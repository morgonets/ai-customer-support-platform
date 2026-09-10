from typing import Annotated

from fastapi import Depends, Request

from app.rag.service import RagService


def get_rag_service(request: Request) -> RagService:
    service: object = request.app.state.rag_service
    if not isinstance(service, RagService):
        raise RuntimeError("RAG service is not configured")
    return service


RagServiceDependency = Annotated[RagService, Depends(get_rag_service)]
