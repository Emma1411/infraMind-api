
from collections.abc import Callable

from models.catalog import PriceItem, PriceStatus
from models.evaluation import CostLine, UnpricedLine
from services.engine.assumptions import SECONDS_PER_REQUEST, Sizing
from services.engine.catalog import HOURS_PER_MONTH, Catalog

SECONDS_PER_MONTH = HOURS_PER_MONTH * 3600

# Paliers de dimensionnement : tier -> élément du catalogue
HETZNER_PLAN = {
    "xs": "hetzner.cpx11",
    "s": "hetzner.cpx21",
    "m": "hetzner.cpx31",
    "l": "hetzner.cpx41",
}

AWS_EC2 = {
    "xs": "aws.ec2.t3_micro",
    "s": "aws.ec2.t3_small",
    "m": "aws.ec2.m7g_large",
    "l": "aws.ec2.m7i_large",
}

AWS_RDS = {
    "xs": "aws.rds.db_t4g_micro",
    "s": "aws.rds.db_t4g_small",
    "m": "aws.rds.db_t4g_medium",
    "l": "aws.rds.db_t4g_medium",
}

AWS_FARGATE = {
    "xs": (0.5, 1.0, 1),
    "s": (1.0, 2.0, 1),
    "m": (2.0, 4.0, 1),
    "l": (2.0, 4.0, 2),
}

AWS_ALB_LCU = {
    "xs": 1,
    "s": 1,
    "m": 2,
    "l": 4,
}

GCP_SQL = {
    "xs": (1, 2.0),
    "s": (1, 4.0),
    "m": (2, 8.0),
    "l": (4, 16.0),
}

GCP_RUN_INSTANCE = {
    "xs": (1.0, 1.0),
    "s": (1.0, 2.0),
    "m": (2.0, 4.0),
    "l": (2.0, 4.0),
}

AZURE_VM = {
    "xs": "azure.vm.b1s",
    "s": "azure.vm.b2s",
    "m": "azure.vm.b2ms",
    "l": "azure.vm.d4s_v5",
}

AZURE_PG = {
    "xs": "azure.postgresql.b1ms",
    "s": "azure.postgresql.b2s",
    "m": "azure.postgresql.b2ms",
    "l": "azure.postgresql.b4ms",
}

# Paliers de trafic sortant.
AWS_EGRESS = [
    ("aws.egress.tier_0_100gb", 100),
    ("aws.egress.tier_100gb_10tb", 10 * 1024),
    ("aws.egress.tier_10_50tb", 50 * 1024),
    ("aws.egress.tier_50_150tb", 150 * 1024),
    ("aws.egress.tier_over_150tb", None),
]

GCP_EGRESS = [
    ("gcp.egress.first_1gib", 1),
    ("gcp.egress.tier_1_1024gib", 1024),
    ("gcp.egress.tier_1024_10240gib", 10 * 1024),
    ("gcp.egress.tier_over_10240gib", None),
]

AZURE_EGRESS = [
    ("azure.egress.first_100gb", 100),
    ("azure.egress.next_10tb", 100 + 10 * 1024),
]


class Estimate:
    """Une estimation mensuelle : lignes chiffrées, lignes sans prix, avertissements."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.lines: list[CostLine] = []
        self.unpriced: list[UnpricedLine] = []
        self.warnings: list[str] = []

    @property
    def total(self) -> float:
        return round(sum(line.monthly for line in self.lines), 2)

    @property
    def complete(self) -> bool:
        return not self.unpriced

    @property
    def needs_verification(self) -> bool:
        return any(line.to_verify for line in self.lines)

    def _unpriced(self, item: PriceItem) -> None:
        self.unpriced.append(
            UnpricedLine(
                item_id=item.id,
                label=item.label,
                reason=item.note or "Prix non fourni",
            )
        )

    def _append(self, item: PriceItem, monthly: float, detail: str) -> None:
        self.lines.append(
            CostLine(
                item_id=item.id,
                label=item.label,
                monthly=round(monthly, 2),
                detail=detail,
                to_verify=item.status == PriceStatus.to_verify,
            )
        )

    def add(
        self,
        item_id: str,
        quantity: float = 1.0,
        detail: str = "",
    ) -> None:
        item = self.catalog.item(item_id)

        if not self.catalog.is_priced(item_id):
            self._unpriced(item)
            return

        self._append(
            item,
            self.catalog.monthly_cost(item_id, quantity),
            detail,
        )

    def add_percent(
        self,
        item_id: str,
        base_monthly: float,
        detail: str = "",
    ) -> None:
        item = self.catalog.item(item_id)

        if not self.catalog.is_priced(item_id):
            self._unpriced(item)
            return

        self._append(
            item,
            base_monthly * self.catalog.amount(item_id) / 100,
            detail,
        )

    def add_metered(
        self,
        item_id: str,
        usage: float,
        detail: str = "",
    ) -> None:
        """Consommation facturée après déduction du quota gratuit mensuel.

        Le quota gratuit est exprimé dans l'unité de facturation de l'entrée
        (par exemple en millions pour les requêtes).
        """
        item = self.catalog.item(item_id)

        if not self.catalog.is_priced(item_id):
            self._unpriced(item)
            return

        free = item.free_quota or 0.0
        billable = max(0.0, usage - free)

        self._append(
            item,
            billable * self.catalog.amount(item_id),
            f"{detail} (quota gratuit déduit : {free:g})",
        )

    def add_tiered_egress(
        self,
        tiers: list[tuple[str, float | None]],
        egress_gb: float,
    ) -> None:
        consumed = 0.0

        for item_id, upto in tiers:
            if consumed >= egress_gb:
                break

            cap = (
                egress_gb
                if upto is None
                else min(egress_gb, float(upto))
            )

            span = cap - consumed

            if span <= 0:
                continue

            item = self.catalog.item(item_id)

            if not self.catalog.is_priced(item_id):
                self._unpriced(item)
            else:
                cost = span * self.catalog.amount(item_id)

                if cost > 0:
                    self._append(
                        item,
                        cost,
                        f"{span:.0f} Go de trafic sortant",
                    )

            consumed = cap

        if consumed < egress_gb - 1e-9:
            self.unpriced.append(
                UnpricedLine(
                    item_id="egress.beyond",
                    label="Trafic sortant au-delà des paliers connus",
                    reason="Tarif non fourni",
                )
            )


def _aws_data(e: Estimate, s: Sizing) -> None:
    if s.has_database:
        rds_id = AWS_RDS[s.tier]
        rds = e.catalog.item(rds_id)

        e.add(
            rds_id,
            1,
            f"{rds.vcpu} vCPU, {rds.ram_gb:g} Gio de RAM, Single-AZ, 730 h",
        )

        storage = max(20.0, s.db_gb)

        e.add(
            "aws.rds.storage_gp3",
            storage,
            f"{storage:.0f} Go provisionnés (minimum de 20 Go supposé)",
        )

    if s.files_gb > 0:
        e.add(
            "aws.s3.standard",
            s.files_gb,
            f"{s.files_gb:.0f} Go de fichiers",
        )


def build_hetzner_vps(catalog: Catalog, s: Sizing) -> Estimate:
    e = Estimate(catalog)

    plan_id = HETZNER_PLAN[s.tier]
    plan = catalog.item(plan_id)

    e.add(
        plan_id,
        1,
        f"{plan.vcpu} vCPU, {plan.ram_gb:g} Go de RAM, {plan.disk_gb} Go de disque",
    )

    if catalog.is_priced(plan_id):
        e.add_percent(
            "hetzner.backup",
            catalog.monthly_cost(plan_id),
            "Sauvegardes automatiques",
        )

    e.add(
        "hetzner.ipv4_primary",
        1,
        "Adresse IPv4 publique",
    )

    usable = max(0.0, (plan.disk_gb or 0) - 15.0)
    extra = max(0.0, s.db_gb + s.files_gb - usable)

    if extra > 0:
        e.add(
            "hetzner.volume",
            extra,
            f"{extra:.0f} Go de volume SSD supplémentaire",
        )

    included = plan.included_traffic_tb

    if included is None:
        included = 1.0
        e.warnings.append(
            "Quota de trafic inclus inconnu pour ce plan : 1 To supposé."
        )

    over = max(0.0, s.egress_gb / 1000 - included)

    if over > 0:
        e.add(
            "hetzner.extra_traffic",
            over,
            f"{over:.2f} To au-delà des {included:g} To inclus",
        )

    if (
        s.files_gb > 0
        and catalog.item("hetzner.object_storage").status
        == PriceStatus.unavailable
    ):
        e.warnings.append(
            "Object Storage indisponible chez Hetzner (États-Unis) : "
            "les fichiers sont stockés sur le serveur."
        )

    return e


def build_aws_ec2_rds(catalog: Catalog, s: Sizing) -> Estimate:
    e = Estimate(catalog)

    ec2_id = AWS_EC2[s.tier]
    ec2 = catalog.item(ec2_id)

    e.add(
        ec2_id,
        1,
        f"{ec2.vcpu} vCPU, {ec2.ram_gb:g} Gio de RAM, 730 h",
    )

    e.add(
        "aws.ebs.gp3",
        30,
        "Disque système de 30 Go",
    )

    e.add(
        "aws.ipv4_public",
        1,
        "Adresse IPv4 publique, 730 h",
    )

    _aws_data(e, s)
    e.add_tiered_egress(AWS_EGRESS, s.egress_gb)

    e.warnings.append(
        "Base en Single-AZ : la haute disponibilité (Multi-AZ) n'est pas chiffrée ici."
    )
    e.warnings.append(
        "Sauvegardes RDS gratuites jusqu'au stockage provisionné ; "
        "au-delà, prix non fourni."
    )

    return e


def build_aws_fargate_rds(catalog: Catalog, s: Sizing) -> Estimate:
    e = Estimate(catalog)

    vcpu, gib, tasks = AWS_FARGATE[s.tier]

    e.add(
        "aws.fargate.vcpu",
        vcpu * tasks,
        f"{tasks} tâche(s) de {vcpu:g} vCPU, 730 h",
    )

    e.add(
        "aws.fargate.memory",
        gib * tasks,
        f"{tasks} tâche(s) de {gib:g} Gio de mémoire, 730 h",
    )

    e.add(
        "aws.alb",
        1,
        "Application Load Balancer, 730 h",
    )

    e.add(
        "aws.alb_lcu",
        AWS_ALB_LCU[s.tier],
        f"{AWS_ALB_LCU[s.tier]} LCU supposés en moyenne",
    )

    e.add(
        "aws.ipv4_public",
        tasks,
        f"{tasks} adresse(s) IPv4 publique(s), 730 h",
    )

    _aws_data(e, s)
    e.add_tiered_egress(AWS_EGRESS, s.egress_gb)

    e.warnings.append(
        "Base en Single-AZ : la haute disponibilité (Multi-AZ) n'est pas chiffrée ici."
    )
    e.warnings.append(
        "Sauvegardes RDS gratuites jusqu'au stockage provisionné ; "
        "au-delà, prix non fourni."
    )

    return e


def build_gcp_cloud_run_sql(catalog: Catalog, s: Sizing) -> Estimate:
    e = Estimate(catalog)

    # Ressources allouées à chaque instance, identiques dans les deux modes de facturation.
    vcpu, gib = GCP_RUN_INSTANCE[s.tier]

    if s.instance_billing:
        e.add_metered(
            "gcp.cloud_run.vcpu_second_instance_based",
            vcpu * SECONDS_PER_MONTH,
            f"{vcpu:g} vCPU alloué en permanence",
        )
        e.add_metered(
            "gcp.cloud_run.memory_second_instance_based",
            gib * SECONDS_PER_MONTH,
            f"{gib:g} Gio alloués en permanence",
        )
        e.warnings.append(
            "Tâches en arrière-plan ou temps réel : Cloud Run est chiffré en mode instance "
            "(CPU toujours alloué)."
        )
    else:
        busy = s.requests_per_month * SECONDS_PER_REQUEST

        e.add_metered(
            "gcp.cloud_run.vcpu_second_request_based",
            busy * vcpu,
            f"{busy * vcpu:,.0f} vCPU-secondes ({vcpu:g} vCPU par instance)",
        )
        e.add_metered(
            "gcp.cloud_run.memory_request_based",
            busy * gib,
            f"{busy * gib:,.0f} Gio-secondes ({gib:g} Gio par instance)",
        )
        e.add_metered(
            "gcp.cloud_run.requests",
            s.requests_per_month / 1_000_000,
            "Requêtes, en millions",
        )
        e.warnings.append(
            "Cloud Run en mode requête : une seule requête à la fois par instance est supposée "
            "(estimation prudente, la concurrence réduit le coût)."
        )

    if s.has_database:
        sql_vcpu, sql_ram = GCP_SQL[s.tier]

        e.add(
            "gcp.cloud_sql.vcpu",
            sql_vcpu,
            f"{sql_vcpu} vCPU",
        )
        e.add(
            "gcp.cloud_sql.ram",
            sql_ram,
            f"{sql_ram:g} Gio de RAM",
        )

        ssd = max(10.0, s.db_gb)

        e.add(
            "gcp.cloud_sql.ssd",
            ssd,
            f"{ssd:.0f} Go de SSD (minimum de 10 Go supposé)",
        )
        e.add(
            "gcp.cloud_sql.backup",
            s.db_gb,
            "Sauvegardes d'une taille supposée égale à la base",
        )

    if s.files_gb > 0:
        e.add(
            "gcp.storage.standard",
            s.files_gb,
            f"{s.files_gb:.0f} Go de fichiers",
        )

    e.add_tiered_egress(GCP_EGRESS, s.egress_gb)

    e.warnings.append(
        "Quotas gratuits Cloud Run appliqués une seule fois par compte de facturation : "
        "s'ils sont déjà consommés par d'autres services, le coût sera plus élevé."
    )
    e.warnings.append(
        "Prix du CPU de Cloud SQL supposé par vCPU et par mois (unité à confirmer)."
    )

    return e


def build_azure_vm_postgres(catalog: Catalog, s: Sizing) -> Estimate:
    e = Estimate(catalog)

    vm_id = AZURE_VM[s.tier]
    vm = catalog.item(vm_id)

    e.add(
        vm_id,
        1,
        f"{vm.vcpu} vCPU, {vm.ram_gb:g} Gio de RAM",
    )

    e.add(
        "azure.disk.premium_ssd_v2_64gib",
        1,
        "Disque système de 64 Gio",
    )

    e.add(
        "azure.ipv4_public",
        1,
        "Adresse IPv4 publique, 730 h",
    )

    if s.has_database:
        pg_id = AZURE_PG[s.tier]
        pg = catalog.item(pg_id)

        e.add(
            pg_id,
            1,
            f"{pg.vcpu} vCPU, {pg.ram_gb:g} Gio de RAM (calcul seul)",
        )

        storage = max(32.0, s.db_gb)

        e.add(
            "azure.postgresql.storage",
            storage,
            f"{storage:.0f} Go provisionnés (minimum de 32 Go supposé)",
        )

    if s.files_gb > 0:
        e.add(
            "azure.blob.hot",
            s.files_gb,
            f"{s.files_gb:.0f} Go de fichiers",
        )

    e.add_tiered_egress(AZURE_EGRESS, s.egress_gb)

    e.warnings.append(
        "Sauvegardes PostgreSQL au-delà du quota inclus : prix non fourni."
    )

    return e


BUILDERS: dict[str, Callable[[Catalog, Sizing], Estimate]] = {
    "hetzner_vps": build_hetzner_vps,
    "aws_ec2_rds": build_aws_ec2_rds,
    "aws_fargate_rds": build_aws_fargate_rds,
    "gcp_cloud_run_sql": build_gcp_cloud_run_sql,
    "azure_vm_postgres": build_azure_vm_postgres,
}
