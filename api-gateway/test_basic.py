#!/usr/bin/env python3
"""
基本功能测试脚本
测试数据库模型和基本API功能
"""

import asyncio
import sqlite3
import os
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database_creation():
    """测试数据库创建"""
    print("测试数据库创建...")
    
    # 创建测试数据库目录
    db_dir = Path("../volume/database")
    db_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = db_dir / "conversations.db"
    
    # 如果数据库存在，先删除
    if db_path.exists():
        db_path.unlink()
    
    # 创建数据库连接
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            api_key VARCHAR(100) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title VARCHAR(200),
            model VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # 创建消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    """)
    
    # 创建请求日志表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            endpoint VARCHAR(100),
            method VARCHAR(10),
            status_code INTEGER,
            response_time FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # 插入测试用户
    cursor.execute("""
        INSERT INTO users (username, api_key) 
        VALUES ('test_user', 'test-api-key-12345')
    """)
    
    # 插入测试会话
    cursor.execute("""
        INSERT INTO sessions (user_id, title, model) 
        VALUES (1, '测试会话', 'qwen2.5-7b')
    """)
    
    # 插入测试消息
    cursor.execute("""
        INSERT INTO messages (session_id, role, content) 
        VALUES (1, 'user', '你好，这是一个测试消息')
    """)
    
    cursor.execute("""
        INSERT INTO messages (session_id, role, content) 
        VALUES (1, 'assistant', '你好！我是AI助手，很高兴为您服务。')
    """)
    
    conn.commit()
    
    # 验证数据
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions")
    session_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM messages")
    message_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"✓ 数据库创建成功")
    print(f"✓ 用户数量: {user_count}")
    print(f"✓ 会话数量: {session_count}")
    print(f"✓ 消息数量: {message_count}")
    
    return True

def test_env_file():
    """测试环境配置文件"""
    print("\n测试环境配置文件...")
    
    env_path = Path("../.env")
    if env_path.exists():
        print("✓ .env 文件存在")
        with open(env_path, 'r') as f:
            content = f.read()
            if 'API_KEY' in content:
                print("✓ API_KEY 配置存在")
            if 'VLLM_URL' in content:
                print("✓ VLLM_URL 配置存在")
            if 'DATABASE_URL' in content:
                print("✓ DATABASE_URL 配置存在")
    else:
        print("✗ .env 文件不存在")
        return False
    
    return True

def test_volume_directories():
    """测试卷目录结构"""
    print("\n测试卷目录结构...")
    
    volume_dir = Path("../volume")
    logs_dir = volume_dir / "logs"
    db_dir = volume_dir / "database"
    
    if volume_dir.exists():
        print("✓ volume 目录存在")
    else:
        print("✗ volume 目录不存在")
        return False
    
    if logs_dir.exists():
        print("✓ logs 目录存在")
    else:
        print("✗ logs 目录不存在")
        return False
    
    if db_dir.exists():
        print("✓ database 目录存在")
    else:
        print("✗ database 目录不存在")
        return False
    
    return True

def main():
    """主测试函数"""
    print("开始基本功能测试...\n")
    
    tests = [
        test_volume_directories,
        test_env_file,
        test_database_creation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    
    print(f"\n测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有基本功能测试通过！")
        return True
    else:
        print("❌ 部分测试失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)