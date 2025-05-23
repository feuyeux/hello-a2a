from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from common.utils.logger import setup_logger
from common.utils.push_notification_auth import PushNotificationSenderAuth
from agents.task_manager import AgentTaskManager
from agents.agent import ElementAgent

logger = setup_logger("HelloA2AServer")

def main(host, port):
    """启动元素查询智能体服务器。"""
    try:
        # 配置智能体能力
        capabilities = AgentCapabilities(
            streaming=True, pushNotifications=True)
        logger.info(
            f"【智能体能力】流式响应={capabilities.streaming}，推送通知={capabilities.pushNotifications}")

        # 定义智能体技能
        skill = AgentSkill(
            id="query_element",
            name="元素周期表工具",
            description="Helps with queries about chemical elements and the periodic table",
            tags=["element", "periodic table", "chemistry"],
            examples=["氢元素的信息", "氢氦锂铍硼"],
        )
        logger.info(f"【智能体技能】{skill.name}")

        # 创建智能体卡片
        agent_card = AgentCard(
            name="Element Agent",
            description="Helps with queries about the periodic table of elements",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=ElementAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ElementAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        logger.info(
            f"【智能体卡片】{agent_card.name} v{agent_card.version}，地址：{agent_card.url}")

        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()

        # 初始化服务器
        logger.info("开始初始化A2A服务器和任务管理器")
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=ElementAgent(
            ), notification_sender_auth=notification_sender_auth),
            host=host,
            port=port,
        )

        # 添加JWKS端点用于推送通知认证
        server.app.add_route(
            "/.well-known/jwks.json", notification_sender_auth.handle_jwks_endpoint, methods=["GET"]
        )
        logger.info("推送通知认证JWKS端点已注册")
        logger.info(f"服务器启动完毕：{host}:{port}")
        server.start()
    except MissingAPIKeyError as e:
        # 处理API密钥缺失错误
        logger.error(f"【错误】API密钥缺失：{e}")
        exit(1)
    except Exception as e:
        # 处理其他异常
        logger.error(f"【错误】服务器启动过程中发生错误：{e}")
        exit(1)


if __name__ == "__main__":
    main( "localhost",10000)
