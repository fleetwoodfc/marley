# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""
sync_ciel - Frappe management command to import CIEL terminology from OCL.

Usage examples::

    bench --site <site> execute healthcare.commands.sync_ciel.sync_ciel

Or (preferred via the frappe commands entry-point registered in hooks.py)::

    bench --site <site> sync-ciel --version latest --make-default
    bench --site <site> sync-ciel --version 2024-01-01 --dry-run
    bench --site <site> sync-ciel --version 2024-01-01 --chunk-size 1000
"""

import sys

import click

import frappe


@click.command("sync-ciel")
@click.option(
	"--version",
	"version_tag",
	default="latest",
	show_default=True,
	help="CIEL version tag to import, or 'latest' to resolve automatically.",
)
@click.option(
	"--make-default",
	is_flag=True,
	default=False,
	help="Promote the imported version to the default after import.",
)
@click.option(
	"--dry-run",
	is_flag=True,
	default=False,
	help="Resolve the version and print what would be imported without writing.",
)
@click.option(
	"--chunk-size",
	default=500,
	show_default=True,
	help="Number of concepts to write in a single DB transaction.",
)
@click.option(
	"--force", is_flag=True, default=False, help="Re-import even if the version is already marked 'ready'."
)
@click.pass_context
def sync_ciel(ctx, version_tag, make_default, dry_run, chunk_size, force):
	"""Import CIEL terminology from OpenConceptLab into Marley."""
	# Frappe commands run inside frappe.init context set up by bench.
	# Import here to avoid circular imports at module load time.
	from healthcare.terminology.importer import CIELImporter

	try:
		importer = CIELImporter()
		summary = importer.import_version(
			version_tag=version_tag,
			make_default=make_default,
			dry_run=dry_run,
			chunk_size=chunk_size,
			force=force,
		)
	except Exception as exc:
		click.echo(f"ERROR: {exc}", err=True)
		sys.exit(1)

	if summary.get("skipped"):
		click.echo(
			f"Skipped: version '{summary['version_tag']}' is already imported. Use --force to re-import."
		)
		return

	if dry_run:
		click.echo(f"[DRY RUN] Would import CIEL version '{summary['version_tag']}'. No changes written.")
		return

	click.echo(
		f"Import complete:\n"
		f"  Version  : {summary['version_tag']}\n"
		f"  Concepts : {summary['concepts_imported']}\n"
		f"  Names    : {summary['names_imported']}\n"
		f"  Mappings : {summary['mappings_imported']}\n"
		f"  Retired  : {summary['concepts_retired']}\n"
		f"  Errors   : {summary['import_errors']}\n"
	)
	if summary["import_errors"]:
		sys.exit(1)
