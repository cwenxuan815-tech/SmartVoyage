#!/bin/bash
# SmartVoyage 容器入口：按 SERVICE_NAME 启动对应进程
set -e
SERVICE_NAME="${1:-api_server}"
echo "=== 启动 SmartVoyage 服务: ${SERVICE_NAME} ==="

case "${SERVICE_NAME}" in
    api_server)
        exec python -m SmartVoyage.api_server ;;
    weather_a2a)
        exec python -m SmartVoyage.a2a_server.weather_server ;;
    ticket_a2a)
        exec python -m SmartVoyage.a2a_server.ticket_server ;;
    trip_a2a)
        exec python -m SmartVoyage.a2a_server.trip_server ;;
    weather_mcp)
        exec python -m SmartVoyage.mcp_server.mcp_weather_server ;;
    ticket_mcp)
        exec python -m SmartVoyage.mcp_server.mcp_ticket_server ;;
    trip_mcp)
        exec python -m SmartVoyage.mcp_server.mcp_trip_server ;;
    init_db)
        exec python scripts/init_db.py --mysql-only ;;
    *)
        echo "未知服务: ${SERVICE_NAME}"
        echo "可用服务: api_server, weather_a2a, ticket_a2a, trip_a2a, weather_mcp, ticket_mcp, trip_mcp, init_db"
        exit 1 ;;
esac
