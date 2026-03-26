"""Information Extraction Module (NER and Entity Linking)"""
from .ner import batch_ner, run_ner_on_text, load_spacy_model
from .ambiguity_tracker import generate_ambiguity_report, flag_ambiguities

__all__ = [
    'batch_ner',
    'run_ner_on_text',
    'load_spacy_model',
    'generate_ambiguity_report',
    'flag_ambiguities',
]
