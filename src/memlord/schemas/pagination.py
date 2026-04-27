import math

from pydantic import BaseModel, Field, computed_field


class Paginated[T: BaseModel](BaseModel):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 0

    @computed_field
    @property
    def total_pages(self) -> int:
        if self.page_size:
            return math.ceil(self.total / self.page_size)
        return 0
