"""Read-side models for the tag network: tags, links between them, clusters."""

from pydantic import BaseModel, ConfigDict, Field


class TagNode(BaseModel):
    """One tag, placed on the network."""

    model_config = ConfigDict(frozen=True)

    tag: str
    photos: int = Field(description="Photos with this tag.")
    cluster: int | None = Field(
        description="Index into TagGraph.clusters; None if the tag has no group."
    )
    x: float
    y: float


class TagLink(BaseModel):
    """Two tags that often appear on the same photos."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    photos: int = Field(description="Photos with both tags.")
    strength: float = Field(ge=0, le=1, description="Jaccard overlap: both / either.")


class TagCluster(BaseModel):
    """A group of tags that go together, biggest tag first."""

    model_config = ConfigDict(frozen=True)

    name: str
    tags: list[str]


class TagGraph(BaseModel):
    """The most-used tags, the links between them and their clusters."""

    model_config = ConfigDict(frozen=True)

    photos: int = Field(description="Photos the graph was built from.")
    nodes: list[TagNode]
    links: list[TagLink]
    clusters: list[TagCluster] = Field(description="Biggest first.")
