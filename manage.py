"""Explicit database initialization; no production migrations during deployment builds."""
import argparse
from database import initialize

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init-db'])
    parser.parse_args()
    initialize()
    print('Database schema is ready. Existing records were preserved.')
