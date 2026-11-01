from models.evaluation import ArchitectureResult
from models.project_spec import ProjectSpec
from services.engine.assumptions import build_sizing
from services.engine.catalog import Catalog
from services.engine.costing import azure_pg_storage
from services.guides.gcp import gcp_safe_name
from services.guides.hetzner import slugify

REGION = "eastus"

VM_SIZES = {
    "azure.vm.b1s": "Standard_B1s",
    "azure.vm.b2s": "Standard_B2s",
    "azure.vm.b2ms": "Standard_B2ms",
    "azure.vm.d2s_v5": "Standard_D2s_v5",
    "azure.vm.d4s_v5": "Standard_D4s_v5",
}

PG_SKUS = {
    "azure.postgresql.b1ms": "Standard_B1ms",
    "azure.postgresql.b2s": "Standard_B2s",
    "azure.postgresql.b2ms": "Standard_B2ms",
    "azure.postgresql.b4ms": "Standard_B4ms",
}

ALLOWED_PARAMS = frozenset(
    {
        "region",
        "app_slug",
        "resource_group",
        "pg_server_name",
        "vm_size",
        "vm_vcpu",
        "vm_ram_gb",
        "pg_sku",
        "pg_vcpu",
        "pg_ram_gb",
        "pg_storage_gb",
        "monthly_total",
        "vm_cost",
        "db_cost",
        "files_cost",
        "network_cost",
    }
)


def build_flags(spec: ProjectSpec) -> frozenset[str]:
    return frozenset({"database"} if build_sizing(spec).has_database else {"no_database"})


def _sum(result: ArchitectureResult, *prefixes: str) -> float:
    return sum(line.monthly for line in result.lines if line.item_id.startswith(prefixes))


def build_params(result: ArchitectureResult, spec: ProjectSpec, catalog: Catalog) -> dict[str, str]:
    sizing = build_sizing(spec)
    vm_line = next((l for l in result.lines if l.item_id in VM_SIZES), None)
    if vm_line is None:
        raise ValueError("Aucune machine virtuelle Azure dans l'estimation.")
    vm = catalog.item(vm_line.item_id)
    slug = slugify(spec.name)

    params = {
        "region": REGION,
        "app_slug": slug,
        "resource_group": f"{slug}-rg",
        "pg_server_name": gcp_safe_name(slug, "-pg"),
        "vm_size": VM_SIZES[vm_line.item_id],
        "vm_vcpu": str(vm.vcpu),
        "vm_ram_gb": f"{vm.ram_gb:g}",
        "monthly_total": f"{result.cost_low:.2f}",
        "vm_cost": f"{_sum(result, 'azure.vm.', 'azure.disk.', 'azure.ipv4'):.2f}",
        "db_cost": f"{_sum(result, 'azure.postgresql.'):.2f}",
        "files_cost": f"{_sum(result, 'azure.blob.'):.2f}",
        "network_cost": f"{_sum(result, 'azure.egress'):.2f}",
        "pg_sku": "",
        "pg_vcpu": "",
        "pg_ram_gb": "",
        "pg_storage_gb": "",
    }

    pg_line = next((l for l in result.lines if l.item_id in PG_SKUS), None)
    if pg_line is not None:
        pg = catalog.item(pg_line.item_id)
        params.update(
            {
                "pg_sku": PG_SKUS[pg_line.item_id],
                "pg_vcpu": str(pg.vcpu),
                "pg_ram_gb": f"{pg.ram_gb:g}",
                "pg_storage_gb": str(azure_pg_storage(sizing.db_gb)),
            }
        )
    return params