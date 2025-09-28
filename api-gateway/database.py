import os
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Base, User
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 数据库配置
DATABASE_DIR = "/app/database"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_DIR}/conversations.db"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_DIR}/conversations.db"

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300
)

# 创建会话工厂
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_database():
    """初始化数据库"""
    try:
        # 确保数据库目录存在
        os.makedirs(DATABASE_DIR, exist_ok=True)
        
        # 创建所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("数据库初始化成功")
        
        # 创建默认用户
        await create_default_user()
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

async def create_default_user():
    """创建默认用户"""
    try:
        async with AsyncSessionLocal() as session:
            # 检查是否已存在默认用户
            from sqlalchemy import select
            result = await session.execute(select(User).where(User.username == "default"))
            existing_user = result.scalar_one_or_none()
            
            if not existing_user:
                default_user = User(
                    username="default",
                    email="default@example.com",
                    api_key="default-api-key",
                    is_active=True
                )
                session.add(default_user)
                await session.commit()
                logger.info("默认用户创建成功")
            else:
                logger.info("默认用户已存在")
                
    except Exception as e:
        logger.error(f"创建默认用户失败: {e}")
        raise

async def close_database():
    """关闭数据库连接"""
    await engine.dispose()
    logger.info("数据库连接已关闭")

def create_sync_engine():
    """创建同步引擎（用于测试或特殊情况）"""
    return create_engine(SYNC_DATABASE_URL, echo=False)

if __name__ == "__main__":
    # 直接运行此脚本时初始化数据库
    asyncio.run(init_database())