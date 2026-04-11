from pydantic import BaseModel


class WorkspaceMessageAnalyticsResponse(BaseModel):
    workspace_id: int
    total_sent: int
    delivered_percentage: float
    read_percentage: float
    failure_percentage: float


class WorkspaceMessageTimelinePoint(BaseModel):
    date: str
    sent: int
    delivered: int


class WorkspaceMessageTimelineResponse(BaseModel):
    workspace_id: int
    points: list[WorkspaceMessageTimelinePoint]
