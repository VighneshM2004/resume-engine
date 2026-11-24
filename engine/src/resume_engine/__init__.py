"""resume_engine: turns resume files into structured candidate profiles.

The pipeline stages (validate, extract, layout, sections, NER, normalize,
dates, confidence) arrive in M2-M3. This package must never import web,
database or queue code: the API worker and the evaluation scripts both
import it, so the F1 we report is the F1 users get.
"""

__version__ = "0.1.0"
