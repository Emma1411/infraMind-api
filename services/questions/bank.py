from models.question import Option, Question, QuestionType


def _opts(*pairs: tuple[str, str]) -> list[Option]:
    return [Option(value=value, label=label) for value, label in pairs]


def _q(
    path: str,
    kind: QuestionType,
    text: str,
    why: str,
    priority: int = 1,
    options: list[Option] | None = None,
) -> Question:
    return Question(
        path=path,
        domain=path.split(".")[0],
        type=kind,
        text=text,
        why=why,
        priority=priority,
        options=options or [],
    )


_QUESTIONS: list[Question] = [
    # ---------- application ----------
    _q(
        "application.app_type", QuestionType.single_choice,
        "Quel type d'application est-ce ?",
        "Le type d'application détermine s'il faut un serveur qui tourne en permanence ou un simple hébergement de fichiers.",
        options=_opts(
            ("static_site", "Site statique (pages fixes, sans serveur)"),
            ("web_app", "Application web avec un serveur"),
            ("api_only", "API seulement (pas d'interface)"),
            ("ssr_app", "Site rendu côté serveur (ex. Next.js)"),
            ("data_pipeline", "Traitement de données planifié"),
            ("other", "Autre"),
        ),
    ),
    _q(
        "application.has_background_jobs", QuestionType.boolean,
        "L'application exécute-t-elle des tâches en arrière-plan (envoi de courriels, rapports, imports) ?",
        "Ces tâches demandent un processus qui tourne en continu, en plus du serveur web.",
    ),
    # ---------- traffic ----------
    _q(
        "traffic.daily_users", QuestionType.single_choice,
        "Combien de personnes utilisent l'application un jour normal ?",
        "Le nombre d'utilisateurs détermine la puissance du serveur et la bande passante nécessaires.",
        options=_opts(
            ("under_100", "Moins de 100"),
            ("between_100_1000", "100 à 1 000"),
            ("between_1000_10000", "1 000 à 10 000"),
            ("over_10000", "Plus de 10 000"),
        ),
    ),
    _q(
        "traffic.has_peaks", QuestionType.boolean,
        "Y a-t-il des moments où le trafic est beaucoup plus élevé (soldes, événements, fin de mois) ?",
        "Un pic peut exiger plus de puissance que la moyenne ne le laisse croire.",
        priority=2,
    ),
    # ---------- data ----------
    _q(
        "data.database_type", QuestionType.single_choice,
        "Quel type de base de données utilise l'application ?",
        "Une base de données demande des sauvegardes et, souvent, un service dédié.",
        options=_opts(
            ("none", "Aucune"),
            ("relational", "Relationnelle (PostgreSQL, MySQL)"),
            ("document", "Documents (MongoDB)"),
            ("key_value", "Clé-valeur (Redis)"),
            ("other", "Autre"),
        ),
    ),
    _q(
        "data.data_size", QuestionType.single_choice,
        "Quelle quantité de données la base contiendra-t-elle dans un an environ ?",
        "La taille détermine le stockage, le coût des sauvegardes et le type de base adapté.",
        options=_opts(
            ("under_1gb", "Moins de 1 Go"),
            ("gb_1_10", "1 à 10 Go"),
            ("gb_10_100", "10 à 100 Go"),
            ("over_100gb", "Plus de 100 Go"),
        ),
    ),
    _q(
        "data.has_file_uploads", QuestionType.boolean,
        "Les utilisateurs peuvent-ils envoyer des fichiers (images, PDF, documents) ?",
        "Les fichiers demandent un espace de stockage séparé et augmentent le transfert de données.",
    ),
    # ---------- backups ----------
    _q(
        "backups.acceptable_data_loss", QuestionType.single_choice,
        "Si le serveur plante, quelle perte de données récentes est acceptable ?",
        "Cela détermine la fréquence des sauvegardes et si une copie en temps réel est nécessaire.",
        options=_opts(
            ("none", "Aucune"),
            ("minutes", "Quelques minutes"),
            ("hours", "Quelques heures"),
            ("one_day", "Jusqu'à une journée"),
        ),
    ),
    _q(
        "backups.acceptable_restore_time", QuestionType.single_choice,
        "Combien de temps l'application peut-elle rester hors service après une panne grave ?",
        "Un redémarrage rapide coûte plus cher qu'une restauration qui prend son temps.",
        options=_opts(
            ("under_1h", "Moins d'une heure"),
            ("few_hours", "Quelques heures"),
            ("one_day", "Une journée"),
            ("several_days", "Plusieurs jours"),
        ),
    ),
    # ---------- compliance ----------
    _q(
        "compliance.personal_data", QuestionType.boolean,
        "L'application stocke-t-elle des données personnelles (noms, courriels, téléphones) ?",
        "Ces données imposent des règles de protection et des exigences de sécurité.",
    ),
    _q(
        "compliance.payment_data", QuestionType.boolean,
        "L'application traite-t-elle des paiements ou des données de carte ?",
        "Cela change fortement les exigences de sécurité.",
    ),
    _q(
        "compliance.health_data", QuestionType.boolean,
        "L'application manipule-t-elle des données de santé ?",
        "Ce sont des données très encadrées par la loi, ce qui limite les choix d'hébergement.",
        priority=2,
    ),
    # ---------- availability ----------
    _q(
        "availability.availability_target", QuestionType.single_choice,
        "Quelle disponibilité le client attend-il ?",
        "Une disponibilité permanente demande de la redondance, donc plus de serveurs et plus de coûts.",
        options=_opts(
            ("best_effort", "Quelques pannes occasionnelles sont acceptables"),
            ("business_hours", "Fiable pendant les heures de bureau"),
            ("always_on", "Disponible en permanence, jour et nuit"),
        ),
    ),
    # ---------- security ----------
    _q(
        "security.auth_required", QuestionType.boolean,
        "Les utilisateurs doivent-ils se connecter avec un compte ?",
        "L'authentification ajoute des exigences de sécurité et de gestion des sessions.",
        priority=2,
    ),
    _q(
        "security.admin_access", QuestionType.boolean,
        "Y a-t-il un espace d'administration ?",
        "Un accès administrateur est une cible : il doit être protégé plus strictement.",
        priority=2,
    ),
    # ---------- network ----------
    _q(
        "network.custom_domain", QuestionType.boolean,
        "Le client veut-il un nom de domaine à son nom (ex. monsalon.ca) ?",
        "Il faut un domaine, un certificat HTTPS et une configuration DNS, avec un petit coût annuel.",
        priority=2,
    ),
    _q(
        "network.sends_emails", QuestionType.boolean,
        "L'application envoie-t-elle des courriels (confirmations, rappels) ?",
        "Les courriels demandent un service d'envoi et une configuration pour ne pas finir dans les indésirables.",
        priority=2,
    ),
    # ---------- delivery ----------
    _q(
        "delivery.environments", QuestionType.multi_choice,
        "Quels environnements faut-il ?",
        "Chaque environnement supplémentaire ajoute un coût et du travail.",
        options=_opts(
            ("dev", "Développement"),
            ("staging", "Test (préproduction)"),
            ("prod", "Production"),
        ),
    ),
    # ---------- observability ----------
    _q(
        "observability.monitoring_level", QuestionType.single_choice,
        "Quel niveau de surveillance faut-il ?",
        "La surveillance détecte les pannes avant le client, mais ajoute un coût et du temps.",
        priority=2,
        options=_opts(
            ("none", "Aucune"),
            ("basic", "De base (le site répond-il ?)"),
            ("full", "Complète (journaux, alertes, métriques)"),
        ),
    ),
    # ---------- team ----------
    _q(
        "team.who_maintains", QuestionType.single_choice,
        "Qui s'occupera de l'infrastructure après la livraison ?",
        "Le temps de maintenance est un coût réel : il doit apparaître dans le devis.",
        options=_opts(
            ("developer", "Moi (le développeur)"),
            ("client", "Le client lui-même"),
            ("client_it", "L'équipe informatique du client"),
            ("nobody", "Personne, elle doit se gérer seule"),
        ),
    ),
    _q(
        "team.ops_skill", QuestionType.single_choice,
        "Quel est le niveau en administration de serveurs de la personne qui maintiendra l'infrastructure ?",
        "Plus la personne est novice, plus il faut privilégier des services gérés, même un peu plus chers.",
        options=_opts(
            ("none", "Débutant"),
            ("basic", "Notions de base"),
            ("advanced", "À l'aise"),
        ),
    ),
    _q(
        "team.hourly_rate", QuestionType.number,
        "Quel est ton tarif horaire pour la maintenance (dans la devise du budget) ?",
        "Il permet de comparer le coût réel de chaque architecture : une infrastructure moins chère à héberger peut coûter plus cher à maintenir.",
        priority=2,
    ),
    # ---------- constraints ----------
    _q(
        "constraints.budget_max_monthly", QuestionType.number,
        "Quel est le budget mensuel maximal pour l'hébergement ?",
        "Un budget impossible à respecter élimine des architectures avant même de les comparer.",
    ),
    _q(
        "constraints.budget_currency", QuestionType.single_choice,
        "Dans quelle devise est ce budget ?",
        "Les fournisseurs facturent en dollars américains ou en euros : on convertit pour comparer.",
        options=_opts(
            ("CAD", "Dollars canadiens"),
            ("USD", "Dollars américains"),
            ("EUR", "Euros"),
        ),
    ),
]

QUESTION_BANK: dict[str, Question] = {q.path: q for q in _QUESTIONS}