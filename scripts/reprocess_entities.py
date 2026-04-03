import os
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.transcript import Transcript
from app.models.capture import CaptureSession
from app.models.assistant import AIExtraction
from app.services.entity_extraction import extract_entities_from_transcript, persist_entities

def reprocess_all_transcripts():
    db: Session = SessionLocal()
    user_id = "43089f63-5519-49c7-92e8-33f8e250dc9d" # Known user ID
    
    try:
        print(f"Fetching all transcripts for user {user_id}...")
        transcripts = db.query(Transcript).all()
        print(f"Found {len(transcripts)} transcripts in database.")
        
        for idx, t in enumerate(transcripts):
            print(f"[{idx+1}/{len(transcripts)}] Processing session {t.session_id}...")
            
            # Find associated extraction ID if any
            extraction = db.query(AIExtraction).filter(AIExtraction.session_id == t.session_id).first()
            extraction_id = extraction.id if extraction else None
            
            # Extract
            entities = extract_entities_from_transcript(t.full_text)
            print(f"  Extracted {len(entities)} potential entities.")
            
            # Persist
            if entities:
                count = persist_entities(db, user_id, t.session_id, extraction_id, entities)
                print(f"  Persisted {count} entity mentions for session {t.session_id}.")
            else:
                print(f"  No entities found for session {t.session_id}.")
                
        print("Re-processing complete.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error during re-processing: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reprocess_all_transcripts()
