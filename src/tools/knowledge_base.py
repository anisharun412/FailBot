"""Knowledge base tool: Lookup known errors with fuzzy matching."""

import json
import logging
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from src.config import get_config


logger = logging.getLogger(__name__)


class KnownErrorsDB:
    """In-memory knowledge base of known errors."""
    
    def __init__(self, db_path: str = "data/known_errors.json"):
        """
        Initialize knowledge base from JSON file.
        
        Args:
            db_path: Path to known_errors.json
        """
        self.db_path = Path(db_path)
        self.errors = []
        self.load()
    
    def load(self):
        """Load known errors from JSON file."""
        if not self.db_path.exists():
            logger.warning(f"Known errors database not found at {self.db_path}")
            self.errors = []
            return
        
        try:
            with open(self.db_path, "r") as f:
                data = json.load(f)
                # Support both "errors" and "patterns" keys for compatibility
                self.errors = data.get("errors") or data.get("patterns", [])
            logger.info(f"Loaded {len(self.errors)} known error patterns")
        except Exception as e:
            logger.error(f"Failed to load known errors: {e}")
            self.errors = []
    
    def lookup(
        self,
        error_signature: str,
        top_k: int = 3,
        threshold: float = 0.80
    ) -> list[dict]:
        """
        Lookup similar known errors using fuzzy matching.
        
        Args:
            error_signature: Error to search for
            top_k: Max number of results to return
            threshold: Minimum similarity score (0.0-1.0)
            
        Returns:
            List of matching error records, sorted by similarity score
        """
        if not self.errors:
            logger.debug("Knowledge base is empty")
            return []
        
        matches = []
        
        for error_record in self.errors:
            signature = error_record.get("signature", "")
            
            # Fuzzy match the error signature
            score = fuzz.token_set_ratio(error_signature.lower(), signature.lower()) / 100.0
            
            if score >= threshold:
                matches.append({
                    **error_record,
                    "match_score": score
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        
        return matches[:top_k]
    
    def add_error(
        self,
        signature: str,
        category: str,
        severity: str,
        description: str,
        common_causes: list[str],
        save: bool = True
    ) -> dict:
        """
        Add a new error pattern to the knowledge base.
        
        Args:
            signature: Error signature
            category: code_bug, flaky, infra, or unknown
            severity: critical, high, medium, or low
            description: Human-readable description
            common_causes: List of typical root causes
            save: Whether to save to disk immediately
            
        Returns:
            The created error record
        """
        error_id = max([e.get("id", 0) for e in self.errors] + [0]) + 1
        
        record = {
            "id": error_id,
            "signature": signature,
            "category": category,
            "severity": severity,
            "description": description,
            "common_causes": common_causes
        }
        
        self.errors.append(record)
        
        if save:
            self.save()
        
        logger.info(f"Added error pattern {error_id}: {signature[:50]}")
        
        return record
    
    def save(self):
        """Save knowledge base to disk."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, "w") as f:
                json.dump({"errors": self.errors}, f, indent=2)
            logger.debug(f"Saved {len(self.errors)} errors to {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to save knowledge base: {e}")


# Global knowledge base instance
_kb_instance: Optional[KnownErrorsDB] = None


def get_knowledge_base(db_path: str = "data/known_errors.json") -> KnownErrorsDB:
    """
    Get or create the global knowledge base instance.
    
    Args:
        db_path: Path to known_errors.json
        
    Returns:
        KnownErrorsDB instance
    """
    global _kb_instance
    
    if _kb_instance is None:
        _kb_instance = KnownErrorsDB(db_path)
    
    return _kb_instance


async def lookup_known_errors(
    error_signature: str,
    top_k: int = 3
) -> list[dict]:
    """
    Look up similar known errors in the knowledge base.
    
    Async wrapper for use in LangGraph nodes.
    
    Args:
        error_signature: Error to search for
        top_k: Max results to return
        
    Returns:
        List of matching known error records
    """
    config = get_config()
    threshold = config.fuzzy_match.get("threshold", 0.80)
    
    kb = get_knowledge_base()
    matches = kb.lookup(error_signature, top_k=top_k, threshold=threshold)
    
    logger.info(f"Knowledge base lookup: found {len(matches)} matches for '{error_signature[:50]}'")
    
    return matches
