from fastapi import APIRouter, Depends

from app.container import Container
from app.db.models import User
from app.deps import get_connection_service, get_container, get_current_user
from app.schemas import ConnectionCreate, ConnectionOut, ConnectionTest, ConnectionTestOut
from app.services.connection_service import ConnectionService

router = APIRouter(prefix="/connections", tags=["connections"])


@router.post("/test", response_model=ConnectionTestOut)
async def test_connection(
    body: ConnectionTest,
    _: User = Depends(get_current_user),
    service: ConnectionService = Depends(get_connection_service),
):
    return ConnectionTestOut(schema_preview=(await service.test(body.url))[:2000])


@router.post("", response_model=ConnectionOut, status_code=201)
async def create_connection(
    body: ConnectionCreate,
    user: User = Depends(get_current_user),
    service: ConnectionService = Depends(get_connection_service),
):
    return await service.create(user.id, body.name, body.url)


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    user: User = Depends(get_current_user),
    service: ConnectionService = Depends(get_connection_service),
):
    return await service.list_all(user.id)


@router.get("/{connection_id}/schema")
async def connection_schema(
    connection_id: str,
    user: User = Depends(get_current_user),
    service: ConnectionService = Depends(get_connection_service),
    container: Container = Depends(get_container),
):
    connection = await service.get_owned(user.id, connection_id)
    info = await container.runner.schema_info(connection.id, service.reveal_url(connection))
    return info.to_dict()


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: str,
    user: User = Depends(get_current_user),
    service: ConnectionService = Depends(get_connection_service),
):
    await service.delete(user.id, connection_id)
