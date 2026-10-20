"""Nightly entry point; accepts the same arguments as manage.py refresh_prices."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sentinel.settings')
from django.core.management import execute_from_command_line
if __name__ == '__main__':
    execute_from_command_line([sys.argv[0], 'refresh_prices', *sys.argv[1:]])
