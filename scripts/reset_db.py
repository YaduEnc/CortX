import sys
import os

# Add project root to path before other imports
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.device import Device
from app.core.security import hash_secret

def reset_db_and_register_device():
    db = SessionLocal()
    try:
        # 1. Delete all data from all tables
        # Order matters due to foreign keys if not using CASCADE TRUNCATE
        # Let's use CASCADE TRUNCATE to be safe and thorough
        tables = [
            "entity_mentions", "entities", "memory_links", "weekly_founder_memos", 
            "founder_signals", "founder_idea_actions", "founder_idea_memories", 
            "founder_idea_clusters", "pending_actions", "contacts", "ai_items", 
            "ai_extractions", "transcript_segments", "transcripts", "audio_chunks", 
            "pairing_sessions", "device_user_bindings", "capture_sessions", 
            "devices", "app_user_preferences", "app_password_reset_tokens", "app_users",
            "founder_idea_clusters", "founder_idea_memories", "founder_idea_actions"
        ]
        
        # Remove duplicates while preserving order (to some extent)
        tables = list(dict.fromkeys(tables))
        
        print("Truncating tables...")
        for table in tables:
            try:
                db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                print(f"  Truncated {table}")
            except Exception as e:
                print(f"  Error truncating {table}: {e}")
        
        db.commit()
        print("All tables truncated.")

        # 2. Register the device
        device_secret = "1234567890"
        for code in ["shashwat"]:
            existing = db.query(Device).filter_by(device_code=code).first()
            if not existing:
                device = Device(
                    device_code=code,
                    secret_hash=hash_secret(device_secret)
                )
                db.add(device)
                print(f"Device registered: code={code}")
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_db_and_register_device()
