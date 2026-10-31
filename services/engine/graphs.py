from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from models.evaluation import ArchitectureGraph, CostLine, GraphEdge, GraphNode

GRAPHS_PATH = Path(__file__).resolve().parents[2] / "data" / "graphs.json"

NodeKind = Literal["user", "compute", "database", "storage", "network", "backup"]


class NodeDef(BaseModel):
    id: str
    label: str
    kind: NodeKind
    description: str = ""
    x: int
    y: int
    # Les lignes de coût dont l'identifiant commence par un de ces préfixes appartiennent à ce nœud
    prefixes: list[str] = Field(default_factory=list)
    # Un nœud optionnel disparaît quand aucune ligne de coût ne lui correspond
    optional: bool = False


class EdgeDef(BaseModel):
    source: str
    target: str
    label: str = ""
    animated: bool = True


class GraphDef(BaseModel):
    nodes: list[NodeDef]
    edges: list[EdgeDef]

    @model_validator(mode="after")
    def _consistent(self) -> "GraphDef":
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Identifiants de nœuds en double")
        if "other" in ids:
            raise ValueError("L'identifiant « other » est réservé")
        known = set(ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"Lien vers un nœud inconnu : {edge.source} -> {edge.target}")
        return self


class GraphsFile(BaseModel):
    graphs: dict[str, GraphDef]


@lru_cache
def get_graphs() -> dict[str, GraphDef]:
    data = GraphsFile.model_validate_json(GRAPHS_PATH.read_text(encoding="utf-8"))
    return data.graphs


def build_graph(arch_id: str, lines: list[CostLine]) -> ArchitectureGraph:
    definition = get_graphs()[arch_id]

    assigned: dict[str, list[CostLine]] = {node.id: [] for node in definition.nodes}
    leftovers: list[CostLine] = []
    for line in lines:
        for node in definition.nodes:
            if any(line.item_id.startswith(prefix) for prefix in node.prefixes):
                assigned[node.id].append(line)
                break
        else:
            leftovers.append(line)

    nodes: list[GraphNode] = []
    for node in definition.nodes:
        node_lines = assigned[node.id]
        if node.optional and not node_lines:
            continue
        nodes.append(
            GraphNode(
                id=node.id,
                label=node.label,
                kind=node.kind,
                description=node.description,
                x=node.x,
                y=node.y,
                monthly_cost=round(sum(line.monthly for line in node_lines), 2),
                lines=node_lines,
            )
        )

    # Filet de sécurité : une ligne sans nœud ne doit jamais disparaître du total
    if leftovers:
        nodes.append(
            GraphNode(
                id="other",
                label="Autres coûts",
                kind="other",
                description="Coûts qui ne correspondent à aucun nœud du schéma.",
                x=0,
                y=340,
                monthly_cost=round(sum(line.monthly for line in leftovers), 2),
                lines=leftovers,
            )
        )

    kept = {node.id for node in nodes}
    edges = [
        GraphEdge(
            id=f"{edge.source}->{edge.target}",
            source=edge.source,
            target=edge.target,
            label=edge.label,
            animated=edge.animated,
        )
        for edge in definition.edges
        if edge.source in kept and edge.target in kept
    ]
    return ArchitectureGraph(nodes=nodes, edges=edges)