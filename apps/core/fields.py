"""SQL types required by the supplied database contract."""
from django.db import models

class FixedCharField(models.CharField):
    def db_type(self, connection):
        return f"char({self.max_length})"
