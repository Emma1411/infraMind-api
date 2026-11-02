from pydantic import BaseModel


class QuoteResponse(BaseModel):
    arch_id: str
    filename: str
    markdown: str
    generated_on: str
    valid_until: str