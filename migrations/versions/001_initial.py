"""Initial serving schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-11-23
"""

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS postgis;

        CREATE SCHEMA IF NOT EXISTS meta;
        CREATE SCHEMA IF NOT EXISTS core;
        CREATE SCHEMA IF NOT EXISTS evidence;
        CREATE SCHEMA IF NOT EXISTS ops;

        CREATE TABLE meta.source_registry (
            source_id text PRIMARY KEY,
            publisher text NOT NULL,
            title text NOT NULL,
            layer_url text NOT NULL,
            coverage_note text NOT NULL,
            record_grain text NOT NULL,
            status text NOT NULL
        );

        CREATE TABLE meta.source_snapshots (
            snapshot_id text PRIMARY KEY,
            source_id text NOT NULL,
            run_id text NOT NULL,
            retrieved_at timestamptz NOT NULL,
            query_text text NOT NULL,
            record_count integer NOT NULL,
            content_hash text NOT NULL,
            bronze_path text NOT NULL,
            source_edited_at timestamptz
        );

        CREATE TABLE core.jurisdictions (
            jurisdiction_id text PRIMARY KEY,
            source_code text NOT NULL,
            name text NOT NULL,
            fips text,
            geom geometry(Geometry, 4326),
            content_hash text NOT NULL,
            retrieved_at timestamptz NOT NULL
        );
        CREATE INDEX jurisdictions_geom_gix ON core.jurisdictions USING gist (geom);

        CREATE TABLE core.parcels (
            folio text PRIMARY KEY,
            parent_folio text,
            condo_flag text,
            site_address text,
            polygon_flag text,
            lon double precision,
            lat double precision,
            geom geometry(Geometry, 4326),
            source_object_id text,
            content_hash text NOT NULL,
            retrieved_at timestamptz NOT NULL
        );
        CREATE INDEX parcels_geom_gix ON core.parcels USING gist (geom);

        CREATE TABLE core.buildings (
            ubid text PRIMARY KEY,
            folio text,
            parent_folio text,
            address text,
            city text,
            municipal_code text,
            units integer,
            floors integer,
            year_built integer,
            bldg_type text,
            geom geometry(Geometry, 4326),
            content_hash text NOT NULL,
            retrieved_at timestamptz NOT NULL
        );

        CREATE TABLE core.property_identities (
            property_id text PRIMARY KEY,
            folio text NOT NULL,
            parent_folio text,
            site_address text,
            condo_flag text,
            jurisdiction_id text,
            jurisdiction_name text,
            match_status text NOT NULL,
            match_method text NOT NULL,
            lon double precision,
            lat double precision,
            geom geometry(Geometry, 4326),
            geometry_kind text NOT NULL,
            limitations text NOT NULL,
            content_hash text NOT NULL,
            retrieved_at timestamptz NOT NULL
        );

        CREATE TABLE evidence.permits (
            source_object_id text PRIMARY KEY,
            permit_number text,
            folio text,
            full_address text,
            permit_status text,
            permit_type text,
            application_type text,
            application_status text,
            scope_of_work text,
            status_at timestamptz,
            source_url text,
            content_hash text NOT NULL,
            raw_json jsonb NOT NULL,
            retrieved_at timestamptz NOT NULL
        );
        CREATE INDEX permits_folio_idx ON evidence.permits (folio);
        CREATE INDEX permits_number_idx ON evidence.permits (permit_number);

        CREATE TABLE evidence.permit_versions (
            source_object_id text NOT NULL,
            content_hash text NOT NULL,
            observed_at timestamptz NOT NULL,
            raw_json jsonb NOT NULL,
            PRIMARY KEY (source_object_id, content_hash)
        );

        CREATE TABLE evidence.flood_findings (
            property_id text PRIMARY KEY,
            zone_code text,
            zone_subtype text,
            elevation double precision,
            source_feature_id text,
            source_layer text NOT NULL,
            source_url text NOT NULL,
            queried_lon double precision,
            queried_lat double precision,
            map_effective_date date,
            limitations text NOT NULL,
            content_hash text NOT NULL,
            retrieved_at timestamptz NOT NULL
        );

        CREATE TABLE ops.ingest_runs (
            run_id text PRIMARY KEY,
            source_id text NOT NULL,
            status text NOT NULL,
            started_at timestamptz NOT NULL,
            finished_at timestamptz,
            rows_read integer NOT NULL DEFAULT 0,
            rows_loaded integer NOT NULL DEFAULT 0,
            rows_rejected integer NOT NULL DEFAULT 0,
            error_message text,
            query_text text
        );

        CREATE TABLE ops.rejected_records (
            rejected_id text PRIMARY KEY,
            run_id text NOT NULL,
            source_id text NOT NULL,
            record_key text,
            reason_code text NOT NULL,
            detail text NOT NULL,
            raw_json jsonb NOT NULL,
            created_at timestamptz NOT NULL
        );

        CREATE TABLE ops.source_coverage (
            property_id text NOT NULL,
            source_id text NOT NULL,
            status text NOT NULL,
            detail text NOT NULL,
            checked_at timestamptz NOT NULL,
            PRIMARY KEY (property_id, source_id)
        );

        CREATE TABLE ops.match_reviews (
            review_id text PRIMARY KEY,
            property_id text NOT NULL,
            method text NOT NULL,
            decision text NOT NULL,
            reason text NOT NULL,
            evidence jsonb NOT NULL,
            created_at timestamptz NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS ops.match_reviews;
        DROP TABLE IF EXISTS ops.source_coverage;
        DROP TABLE IF EXISTS ops.rejected_records;
        DROP TABLE IF EXISTS ops.ingest_runs;
        DROP TABLE IF EXISTS evidence.flood_findings;
        DROP TABLE IF EXISTS evidence.permit_versions;
        DROP TABLE IF EXISTS evidence.permits;
        DROP TABLE IF EXISTS core.property_identities;
        DROP TABLE IF EXISTS core.buildings;
        DROP TABLE IF EXISTS core.parcels;
        DROP TABLE IF EXISTS core.jurisdictions;
        DROP TABLE IF EXISTS meta.source_snapshots;
        DROP TABLE IF EXISTS meta.source_registry;
        DROP SCHEMA IF EXISTS ops CASCADE;
        DROP SCHEMA IF EXISTS evidence CASCADE;
        DROP SCHEMA IF EXISTS core CASCADE;
        DROP SCHEMA IF EXISTS meta CASCADE;
        """
    )
