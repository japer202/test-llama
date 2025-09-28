from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import os
import json
import time
from datetime import datetime
import logging
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

# 导入数据库相关模块
from database import get_db, init_database, close_database
from models import User, Session, Message, RequestLog

# Pydantic模型定义
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: Optional[str] = "qwen2.5-7b"
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    user_id: Optional[str] = "default"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

class SessionCreate(BaseModel):
    title: Optional[str] = None
    model_name: Optional[str] = "qwen2.5-7b"
    system_prompt: Optional[str] = None
    user_id: Optional[str] = "default"

class SessionResponse(BaseModel):
    id: str
    title: Optional[str]
    model_name: str
    system_prompt: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    token_count: int
    created_at: datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/access.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Qwen API Gateway with Conversation Storage", version="2.0.0")

# 允许跨域请求（方便本地开发）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 应用启动和关闭事件
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    await init_database()
    logger.info("应用启动完成，数据库已初始化")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    await close_database()
    logger.info("应用已关闭，数据库连接已清理")

# 配置
API_KEY = os.getenv('API_KEY', 'default_key')
VLLM_URL = os.getenv('VLLM_URL', 'http://localhost:8001')
ALLOWED_IPS = os.getenv('ALLOWED_IPS', '').split(',') if os.getenv('ALLOWED_IPS') else []
LOG_REQUESTS = os.getenv('LOG_REQUESTS', 'true').lower() == 'true'

security = HTTPBearer()

class SimpleAuth:
    def __init__(self):
        self.api_key = API_KEY
        self.allowed_ips = [ip.strip() for ip in ALLOWED_IPS if ip.strip()]
    
    def verify_api_key(self, token: str) -> bool:
        """验证API密钥"""
        return token == self.api_key
    
    def check_ip_allowed(self, ip: str) -> bool:
        """检查IP是否允许访问"""
        if not self.allowed_ips:
            return True  # 如果没有设置IP限制，则允许所有IP
        
        for allowed_ip in self.allowed_ips:
            if '/' in allowed_ip:  # CIDR格式
                import ipaddress
                try:
                    if ipaddress.ip_address(ip) in ipaddress.ip_network(allowed_ip, strict=False):
                        return True
                except:
                    continue
            else:  # 单个IP
                if ip == allowed_ip:
                    return True
        return False
    
    def log_request(self, ip: str, endpoint: str, status: str, details: dict = None):
        """记录请求日志"""
        if LOG_REQUESTS:
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'ip': ip,
                'endpoint': endpoint,
                'status': status,
                'details': details or {}
            }
            logger.info(f"REQUEST: {json.dumps(log_data)}")

auth = SimpleAuth()

async def verify_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证请求认证"""
    client_ip = request.client.host
    
    # 检查IP限制
    if not auth.check_ip_allowed(client_ip):
        auth.log_request(client_ip, request.url.path, "IP_BLOCKED")
        raise HTTPException(status_code=403, detail="IP not allowed")
    
    # 验证API密钥
    if not auth.verify_api_key(credentials.credentials):
        auth.log_request(client_ip, request.url.path, "AUTH_FAILED", 
                        {'reason': 'Invalid API key'})
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return client_ip

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Qwen API Gateway with Conversation Storage",
        "version": "2.0.0",
        "endpoints": {
            "chat": "/v1/chat/completions",
            "models": "/v1/models",
            "health": "/health",
            "sessions": {
                "create": "POST /v1/sessions",
                "list": "GET /v1/sessions",
                "get": "GET /v1/sessions/{session_id}",
                "delete": "DELETE /v1/sessions/{session_id}",
                "messages": "GET /v1/sessions/{session_id}/messages"
            },
            "stats": "/stats"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{VLLM_URL}/health", timeout=5.0)
            vllm_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        vllm_status = "unhealthy"
    
    return {
        "status": "healthy",
        "vllm_status": vllm_status,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/v1/models")
async def list_models(client_ip: str = Depends(verify_token)):
    """获取可用模型列表"""
    auth.log_request(client_ip, "/v1/models", "SUCCESS")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{VLLM_URL}/v1/models", timeout=10.0)
            return response.json()
    except Exception as e:
        auth.log_request(client_ip, "/v1/models", "ERROR", {'error': str(e)})
        raise HTTPException(status_code=500, detail="Failed to get models")

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, chat_request: ChatRequest, 
                          client_ip: str = Depends(verify_token),
                          db: AsyncSession = Depends(get_db)):
    """聊天完成接口（带对话存储）"""
    start_time = time.time()
    
    try:
        # 获取或创建用户
        user = await get_or_create_user(db, chat_request.user_id)
        
        # 获取或创建会话
        session = None
        if chat_request.session_id:
            session = await get_session_by_id(db, chat_request.session_id, user.id)
        
        if not session:
            # 创建新会话
            session = await create_new_session(db, user.id, chat_request.model, 
                                             title=f"对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # 存储用户消息
        user_message = None
        if chat_request.messages:
            last_message = chat_request.messages[-1]
            if last_message.role == "user":
                user_message = await store_message(db, session.id, "user", last_message.content)
        
        # 记录请求开始
        auth.log_request(client_ip, "/v1/chat/completions", "START", {
            'model': chat_request.model,
            'session_id': session.id,
            'user_id': user.id,
            'messages_count': len(chat_request.messages)
        })
        
        # 准备发送给vLLM的请求
        vllm_request = {
            "model": chat_request.model,
            "messages": [msg.dict() for msg in chat_request.messages],
            "temperature": chat_request.temperature,
            "stream": chat_request.stream
        }
        
        if chat_request.max_tokens:
            vllm_request["max_tokens"] = chat_request.max_tokens
        
        # 转发请求到vLLM
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{VLLM_URL}/v1/chat/completions",
                json=vllm_request,
                timeout=120.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"vLLM error: {response.text}"
                )
            
            response_data = response.json()
        
        # 存储助手回复
        assistant_message = None
        if response_data.get('choices') and len(response_data['choices']) > 0:
            assistant_content = response_data['choices'][0]['message']['content']
            assistant_message = await store_message(db, session.id, "assistant", assistant_content,
                                                  token_count=response_data.get('usage', {}).get('completion_tokens', 0))
        
        # 更新会话时间
        await update_session_timestamp(db, session.id)
        
        # 记录请求日志到数据库
        await log_request_to_db(db, user.id, session.id, "/v1/chat/completions", "POST", 
                               client_ip, request.headers.get("user-agent"), 
                               json.dumps(vllm_request), 200, int((time.time() - start_time) * 1000))
        
        # 在响应中添加会话信息
        response_data['session_id'] = session.id
        response_data['user_id'] = user.id
        
        # 记录成功响应
        response_time = time.time() - start_time
        auth.log_request(client_ip, "/v1/chat/completions", "SUCCESS", {
            'response_time': round(response_time, 3),
            'tokens_used': response_data.get('usage', {}).get('total_tokens', 0),
            'model': response_data.get('model'),
            'session_id': session.id
        })
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        response_time = time.time() - start_time
        auth.log_request(client_ip, "/v1/chat/completions", "ERROR", {
            'error': str(e),
            'response_time': round(response_time, 3)
        })
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

# 数据库辅助函数
async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """获取或创建用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(id=user_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    return user

async def create_new_session(db: AsyncSession, user_id: str, model_name: str, title: str = None) -> Session:
    """创建新会话"""
    import uuid
    
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title or f"对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        model_name=model_name
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    return session

async def get_session_by_id(db: AsyncSession, session_id: str, user_id: str) -> Optional[Session]:
    """根据ID获取会话"""
    result = await db.execute(
        select(Session).where(
            and_(Session.id == session_id, Session.user_id == user_id)
        )
    )
    return result.scalar_one_or_none()

async def store_message(db: AsyncSession, session_id: str, role: str, content: str, token_count: int = 0) -> Message:
    """存储消息"""
    import uuid
    
    message = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role=role,
        content=content,
        token_count=token_count
    )
    
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    return message

async def update_session_timestamp(db: AsyncSession, session_id: str):
    """更新会话时间戳"""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    
    if session:
        session.updated_at = datetime.now()
        await db.commit()

async def log_request_to_db(db: AsyncSession, user_id: str, session_id: str, endpoint: str, 
                           method: str, ip_address: str, user_agent: str, 
                           request_data: str, response_status: int, response_time_ms: int):
    """记录请求到数据库"""
    import uuid
    
    log_entry = RequestLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        endpoint=endpoint,
        method=method,
        ip_address=ip_address,
        user_agent=user_agent,
        request_data=request_data,
        response_status=response_status,
        response_time_ms=response_time_ms
    )
    
    db.add(log_entry)
    await db.commit()

# 会话管理API
@app.post("/v1/sessions", response_model=SessionResponse)
async def create_session(session_data: SessionCreate, 
                        client_ip: str = Depends(verify_token),
                        db: AsyncSession = Depends(get_db)):
    """创建新会话"""
    try:
        # 获取或创建用户
        user = await get_or_create_user(db, session_data.user_id)
        
        # 创建会话
        session = await create_new_session(db, user.id, session_data.model, session_data.title)
        
        return SessionResponse(
            id=session.id,
            title=session.title,
            model=session.model_name,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=0
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@app.get("/v1/sessions", response_model=List[SessionResponse])
async def list_sessions(user_id: str = "default", 
                       client_ip: str = Depends(verify_token),
                       db: AsyncSession = Depends(get_db)):
    """获取用户的所有会话"""
    try:
         # 获取用户
        user = await get_or_create_user(db, user_id)
        
        # 查询会话
        result = await db.execute(
            select(Session, func.count(Message.id).label('message_count'))
            .outerjoin(Message, Session.id == Message.session_id)
            .where(Session.user_id == user.id)
            .group_by(Session.id)
            .order_by(desc(Session.updated_at))
        )
        
        sessions = []
        for session, message_count in result.all():
            sessions.append(SessionResponse(
                 id=session.id,
                 title=session.title,
                 model=session.model_name,
                 created_at=session.created_at,
                 updated_at=session.updated_at,
                 message_count=message_count or 0
             ))
        
        return sessions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

@app.get("/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, user_id: str = "default",
                     client_ip: str = Depends(verify_token),
                     db: AsyncSession = Depends(get_db)):
    """获取特定会话信息"""
    try:
         user = await get_or_create_user(db, user_id)
        session = await get_session_by_id(db, session_id, user.id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # 获取消息数量
        result = await db.execute(
            select(func.count(Message.id)).where(Message.session_id == session.id)
        )
        message_count = result.scalar() or 0
        
        return SessionResponse(
             id=session.id,
             title=session.title,
             model=session.model_name,
             created_at=session.created_at,
             updated_at=session.updated_at,
             message_count=message_count
         )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")

@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = "default",
                        client_ip: str = Depends(verify_token),
                        db: AsyncSession = Depends(get_db)):
    """删除会话"""
    try:
        user = await get_or_create_user(db, user_id)
        session = await get_session_by_id(db, session_id, user.id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # 删除会话（级联删除消息）
        await db.delete(session)
        await db.commit()
        
        return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@app.get("/v1/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(session_id: str, user_id: str = "default",
                              client_ip: str = Depends(verify_token),
                              db: AsyncSession = Depends(get_db)):
    """获取会话的所有消息"""
    try:
        user = await get_or_create_user(db, user_id)
        session = await get_session_by_id(db, session_id, user.id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # 查询消息
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session.id)
            .order_by(Message.created_at)
        )
        
        messages = []
        for message in result.scalars().all():
            messages.append(MessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                token_count=message.token_count,
                created_at=message.created_at
            ))
        
        return messages
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")

@app.get("/stats")
async def get_stats(client_ip: str = Depends(verify_token)):
    """获取简单的使用统计"""
    try:
        # 读取今天的日志统计
        import re
        from collections import defaultdict
        
        stats = defaultdict(int)
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            with open('/app/logs/access.log', 'r') as f:
                for line in f:
                    if today in line and 'REQUEST:' in line:
                        if '"status": "SUCCESS"' in line:
                            stats['successful_requests'] += 1
                        elif '"status": "ERROR"' in line:
                            stats['failed_requests'] += 1
                        elif '"status": "AUTH_FAILED"' in line:
                            stats['auth_failures'] += 1
        except FileNotFoundError:
            pass
        
        return {
            'date': today,
            'stats': dict(stats),
            'total_requests': sum(stats.values())
        }
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)