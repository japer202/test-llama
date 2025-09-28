#!/usr/bin/env python3
"""
简化的API功能测试
使用内置库测试核心API逻辑
"""

import json
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class SimpleAPITest:
    def __init__(self):
        self.db_path = Path("../volume/database/conversations.db")
        
    def get_db_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path))
    
    def test_user_management(self):
        """测试用户管理功能"""
        print("测试用户管理功能...")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 测试获取用户
        cursor.execute("SELECT * FROM users WHERE api_key = ?", ("test-api-key-12345",))
        user = cursor.fetchone()
        
        if user:
            print(f"✓ 用户验证成功: {user[1]} (ID: {user[0]})")
            conn.close()
            return user[0]  # 返回用户ID
        else:
            print("✗ 用户验证失败")
            conn.close()
            return None
    
    def test_session_management(self, user_id):
        """测试会话管理功能"""
        print("\n测试会话管理功能...")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 创建新会话
        cursor.execute("""
            INSERT INTO sessions (user_id, title, model) 
            VALUES (?, ?, ?)
        """, (user_id, "API测试会话", "qwen2.5-7b"))
        
        session_id = cursor.lastrowid
        conn.commit()
        
        print(f"✓ 创建会话成功: ID {session_id}")
        
        # 获取用户所有会话
        cursor.execute("""
            SELECT id, title, model, created_at 
            FROM sessions 
            WHERE user_id = ? 
            ORDER BY updated_at DESC
        """, (user_id,))
        
        sessions = cursor.fetchall()
        print(f"✓ 用户会话数量: {len(sessions)}")
        
        for session in sessions:
            print(f"  - 会话 {session[0]}: {session[1]} ({session[2]})")
        
        conn.close()
        return session_id
    
    def test_message_storage(self, session_id):
        """测试消息存储功能"""
        print("\n测试消息存储功能...")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 添加用户消息
        cursor.execute("""
            INSERT INTO messages (session_id, role, content) 
            VALUES (?, ?, ?)
        """, (session_id, "user", "这是一个API测试消息"))
        
        # 添加助手回复
        cursor.execute("""
            INSERT INTO messages (session_id, role, content) 
            VALUES (?, ?, ?)
        """, (session_id, "assistant", "收到您的测试消息，API功能正常工作。"))
        
        conn.commit()
        
        # 获取会话消息
        cursor.execute("""
            SELECT role, content, created_at 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY created_at ASC
        """, (session_id,))
        
        messages = cursor.fetchall()
        print(f"✓ 会话消息数量: {len(messages)}")
        
        for i, msg in enumerate(messages):
            print(f"  {i+1}. [{msg[0]}]: {msg[1][:50]}...")
        
        conn.close()
        return len(messages)
    
    def test_request_logging(self, user_id):
        """测试请求日志功能"""
        print("\n测试请求日志功能...")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 模拟API请求日志
        cursor.execute("""
            INSERT INTO request_logs (user_id, endpoint, method, status_code, response_time) 
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, "/v1/chat/completions", "POST", 200, 1.25))
        
        cursor.execute("""
            INSERT INTO request_logs (user_id, endpoint, method, status_code, response_time) 
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, "/v1/sessions", "GET", 200, 0.15))
        
        conn.commit()
        
        # 获取请求统计
        cursor.execute("""
            SELECT COUNT(*) as total_requests,
                   AVG(response_time) as avg_response_time,
                   COUNT(CASE WHEN status_code = 200 THEN 1 END) as successful_requests
            FROM request_logs 
            WHERE user_id = ?
        """, (user_id,))
        
        stats = cursor.fetchone()
        
        print(f"✓ 总请求数: {stats[0]}")
        print(f"✓ 平均响应时间: {stats[1]:.2f}s")
        print(f"✓ 成功请求数: {stats[2]}")
        
        conn.close()
        return stats
    
    def test_data_integrity(self):
        """测试数据完整性"""
        print("\n测试数据完整性...")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 检查外键关系
        cursor.execute("""
            SELECT s.id, s.title, u.username 
            FROM sessions s 
            JOIN users u ON s.user_id = u.id
        """)
        
        session_user_joins = cursor.fetchall()
        print(f"✓ 会话-用户关联数: {len(session_user_joins)}")
        
        cursor.execute("""
            SELECT m.id, m.role, s.title 
            FROM messages m 
            JOIN sessions s ON m.session_id = s.id
        """)
        
        message_session_joins = cursor.fetchall()
        print(f"✓ 消息-会话关联数: {len(message_session_joins)}")
        
        conn.close()
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始API功能测试...\n")
        
        try:
            # 测试用户管理
            user_id = self.test_user_management()
            if not user_id:
                return False
            
            # 测试会话管理
            session_id = self.test_session_management(user_id)
            if not session_id:
                return False
            
            # 测试消息存储
            message_count = self.test_message_storage(session_id)
            if message_count == 0:
                return False
            
            # 测试请求日志
            stats = self.test_request_logging(user_id)
            if not stats:
                return False
            
            # 测试数据完整性
            if not self.test_data_integrity():
                return False
            
            print("\n🎉 所有API功能测试通过！")
            return True
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            return False

def main():
    """主函数"""
    # 确保数据库存在
    db_path = Path("../volume/database/conversations.db")
    if not db_path.exists():
        print("❌ 数据库不存在，请先运行 test_basic.py")
        return False
    
    # 运行API测试
    tester = SimpleAPITest()
    success = tester.run_all_tests()
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)