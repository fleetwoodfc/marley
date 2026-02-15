#!/usr/bin/env python3
"""Script to build local RadLex index from CSV.

Usage:
  python build_radlex_index.py --csv /path/to/playbook.csv [--db /path/to/radlex.db]
"""
import argparse
from healthcare.healthcare.radlex_index import build_index_from_csv


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', required=True)
    p.add_argument('--db')
    args = p.parse_args()
    build_index_from_csv(args.csv, args.db)


if __name__ == '__main__':
    main()
