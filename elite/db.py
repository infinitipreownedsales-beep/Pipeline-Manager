"""Durable authoritative persistence: SQLite connection + tracked migrations.

SQLite (stdlib) is the authoritative store. It is a real file that survives
process restart and is independent of any browser-local state. Migrations are
ordered, tracked in `migration_record`, and idempotent to re-run.
"""
from __future__ import annotations

import sqlite3

from .errors import MigrationError, PersistenceError


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


# Ordered migrations. Each is (version, name, SQL). Append-only history; never edit
# a released migration in place.
MIGRATIONS = [
    (1, "platform_core", """
        CREATE TABLE system_metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE principal (
            id          TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            secret_hash TEXT NOT NULL,
            secret_salt TEXT NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            version     INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE capability_grant (
            id           TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL REFERENCES principal(id),
            capability   TEXT NOT NULL,
            authority    TEXT NOT NULL,
            scope        TEXT NOT NULL,
            active       INTEGER NOT NULL DEFAULT 1,
            granted_at   TEXT NOT NULL,
            revoked_at   TEXT,
            version      INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE audit_event (
            id             TEXT PRIMARY KEY,
            actor          TEXT NOT NULL,
            delegated_actor TEXT,
            action         TEXT NOT NULL,
            target_ref     TEXT,
            scope          TEXT,
            environment    TEXT NOT NULL,
            occurred_at    TEXT NOT NULL,
            result         TEXT NOT NULL,
            correlation_id TEXT,
            prior_ref      TEXT,
            resulting_ref  TEXT
        );
        -- Audit is append-only, enforced below the application:
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_event
            BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
        CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_event
            BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
        CREATE TABLE idempotency_record (
            key        TEXT PRIMARY KEY,
            result_ref TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE persistence_probe (
            id         TEXT PRIMARY KEY,
            note       TEXT,
            created_at TEXT NOT NULL
        );
    """),
    (2, "data_identity_facts", """
        -- Source registry + contracts
        CREATE TABLE source_registry (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, owner TEXT, source_type TEXT,
            supported_profiles TEXT, authoritative_fact_types TEXT, scope TEXT,
            status TEXT NOT NULL, effective_from TEXT, effective_to TEXT,
            registered_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE schema_profile (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES source_registry(id),
            version INTEGER NOT NULL, fields TEXT NOT NULL, snapshot_capable INTEGER NOT NULL DEFAULT 0,
            full_snapshot_requirements TEXT, scope_rules TEXT, effective_time_rule TEXT,
            compatibility_status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
            UNIQUE(source_id, version)
        );
        -- Raw payload preservation + replay identity
        CREATE TABLE import_payload (
            checksum TEXT PRIMARY KEY, raw_text TEXT NOT NULL,
            first_batch_id TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE import_batch (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, schema_profile_version INTEGER,
            payload_checksum TEXT NOT NULL, received_at TEXT NOT NULL, effective_time TEXT,
            store_scope TEXT, claimed_snapshot_type TEXT, validated_snapshot_type TEXT,
            lifecycle_status TEXT NOT NULL, row_count INTEGER NOT NULL DEFAULT 0,
            accepted_count INTEGER DEFAULT 0, rejected_count INTEGER DEFAULT 0,
            quarantined_count INTEGER DEFAULT 0, duplicate_count INTEGER DEFAULT 0,
            conflicting_count INTEGER DEFAULT 0, unresolved_count INTEGER DEFAULT 0,
            detail TEXT, correlation_id TEXT, replay_of TEXT
        );
        CREATE TABLE source_observation (
            id TEXT PRIMARY KEY, import_batch_id TEXT NOT NULL REFERENCES import_batch(id),
            source_record_identity TEXT, raw_values TEXT NOT NULL, normalized_values TEXT NOT NULL,
            observed_time TEXT, recorded_time TEXT NOT NULL, source_scope TEXT,
            validation_status TEXT NOT NULL, identity_status TEXT, acceptance_status TEXT NOT NULL,
            provenance TEXT, supersedes_ref TEXT, correction_ref TEXT
        );
        -- Canonical identity
        CREATE TABLE vehicle_unit (
            id TEXT PRIMARY KEY, vin TEXT, identity_status TEXT NOT NULL, store_scope TEXT NOT NULL,
            created_at TEXT NOT NULL, corrected_at TEXT, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE production_order (
            id TEXT PRIMARY KEY, manufacturer_order_id TEXT, vin TEXT,
            linked_vehicle_unit_id TEXT, identity_status TEXT NOT NULL, store_scope TEXT NOT NULL,
            created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE entity_alias (
            id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            alias_type TEXT NOT NULL, alias_value TEXT NOT NULL, store_scope TEXT,
            source_ref TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE identity_evidence (
            id TEXT PRIMARY KEY, source_ref TEXT, record_ref TEXT, entity_type TEXT,
            identifier_type TEXT, identifier_value TEXT, candidate_entities TEXT,
            resolution_status TEXT NOT NULL, resolution_rule_version TEXT, confidence REAL,
            resolver TEXT, reason TEXT, recorded_at TEXT NOT NULL, correction_ref TEXT, store_scope TEXT
        );
        -- Business facts (append-preserving) + relationships
        CREATE TABLE business_fact (
            id TEXT PRIMARY KEY, fact_type TEXT NOT NULL, subject_entity_type TEXT,
            subject_entity_id TEXT, payload TEXT, effective_time TEXT, recorded_time TEXT NOT NULL,
            observation_refs TEXT, source_authority TEXT, quality_status TEXT,
            status TEXT NOT NULL, correction_of TEXT, superseded_by TEXT, reversal_of TEXT,
            store_scope TEXT, provenance TEXT, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TRIGGER business_fact_no_delete BEFORE DELETE ON business_fact
            BEGIN SELECT RAISE(ABORT, 'business_fact history is preserved'); END;
        CREATE TABLE reconciliation_result (
            id TEXT PRIMARY KEY, import_batch_id TEXT NOT NULL REFERENCES import_batch(id),
            source_observation_id TEXT, candidate_entities TEXT, outcome TEXT NOT NULL,
            reason TEXT, resulting_fact_refs TEXT, conflict_refs TEXT, reviewer TEXT,
            recorded_at TEXT NOT NULL
        );
    """),
    (3, "policy_and_versioning", """
        CREATE TABLE policy_family (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, owning_domain TEXT,
            value_schema TEXT, allowed_scope_dimensions TEXT, default_resolution TEXT,
            approval_required INTEGER NOT NULL DEFAULT 1, correction_rules TEXT,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
        );
        CREATE TABLE policy_version (
            id TEXT PRIMARY KEY, family_id TEXT NOT NULL REFERENCES policy_family(id),
            version_number INTEGER NOT NULL, value TEXT NOT NULL, source TEXT, evidence_refs TEXT,
            scope TEXT, effective_start TEXT, effective_end TEXT,
            start_inclusive INTEGER NOT NULL DEFAULT 1, end_inclusive INTEGER NOT NULL DEFAULT 0,
            recorded_time TEXT NOT NULL, approval_state TEXT NOT NULL DEFAULT 'unapproved',
            approving_principal TEXT, approved_time TEXT, scheduled_activation TEXT,
            lifecycle_status TEXT NOT NULL, supersedes TEXT, superseded_by TEXT, correction_of TEXT,
            revocation TEXT, reason TEXT, provenance TEXT, store_scope TEXT,
            is_scenario INTEGER NOT NULL DEFAULT 0, scenario_id TEXT, version INTEGER NOT NULL DEFAULT 1
        );
        -- immutable value payload; append-preserving history
        CREATE TRIGGER policy_version_value_immutable BEFORE UPDATE OF value ON policy_version
            WHEN NEW.value <> OLD.value
            BEGIN SELECT RAISE(ABORT, 'policy_version.value is immutable'); END;
        CREATE TRIGGER policy_version_no_delete BEFORE DELETE ON policy_version
            BEGIN SELECT RAISE(ABORT, 'policy_version history is preserved'); END;
        CREATE TABLE calculation_family (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, owning_domain TEXT, purpose TEXT,
            input_contract_version TEXT, output_contract_version TEXT, determinism TEXT,
            required_policy_families TEXT, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
        );
        CREATE TABLE calculation_version (
            id TEXT PRIMARY KEY, family_id TEXT NOT NULL REFERENCES calculation_family(id),
            semver TEXT NOT NULL, impl_revision TEXT, input_contract_version TEXT, output_contract_version TEXT,
            required_policy_families TEXT, effective_start TEXT, effective_end TEXT,
            lifecycle_status TEXT NOT NULL, approval_metadata TEXT, supersedes TEXT, superseded_by TEXT,
            rollback_of TEXT, change_summary TEXT, reproducibility_metadata TEXT, created_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TRIGGER calc_version_no_delete BEFORE DELETE ON calculation_version
            BEGIN SELECT RAISE(ABORT, 'calculation_version history is preserved'); END;
        CREATE TABLE model_version (
            id TEXT PRIMARY KEY, model_family TEXT NOT NULL, version TEXT NOT NULL, scope TEXT,
            purpose TEXT, status TEXT NOT NULL DEFAULT 'registered', activation TEXT, supersedes TEXT,
            evidence_refs TEXT, calibration_proposal TEXT, validation_status TEXT, rollback_ref TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE identity_rule_version (
            id TEXT PRIMARY KEY, rule_family TEXT NOT NULL, version TEXT NOT NULL, entity_types TEXT,
            rule_summary TEXT, impl_revision TEXT, status TEXT NOT NULL DEFAULT 'registered',
            effective_start TEXT, effective_end TEXT, approval_metadata TEXT, supersedes TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE comparison_specification_version (
            id TEXT PRIMARY KEY, version TEXT NOT NULL, prediction_type TEXT, observation_type TEXT,
            subject_entity_type TEXT, timing_rules TEXT, matching_rules TEXT, unit_contract TEXT,
            status TEXT NOT NULL DEFAULT 'registered', effective_start TEXT, effective_end TEXT,
            approval_metadata TEXT, supersedes TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE reproducibility_package (
            id TEXT PRIMARY KEY, refs TEXT NOT NULL, dealership_tz TEXT, calculation_timestamp TEXT,
            implementation_revision TEXT, output_reference TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE version_activation_history (
            id TEXT PRIMARY KEY, target_type TEXT NOT NULL, target_id TEXT NOT NULL, action TEXT NOT NULL,
            actor TEXT, at TEXT NOT NULL, detail TEXT
        );
        CREATE TABLE version_rollback_history (
            id TEXT PRIMARY KEY, target_type TEXT NOT NULL, from_id TEXT, to_id TEXT, actor TEXT,
            at TEXT NOT NULL, reason TEXT
        );
    """),
    (4, "new_inventory", """
        -- Sellable Combination: a canonical orderable + sellable configuration.
        CREATE TABLE sellable_combination (
            id TEXT PRIMARY KEY, store_scope TEXT NOT NULL, franchise TEXT, model TEXT NOT NULL,
            model_year TEXT, trim TEXT, drivetrain TEXT, exterior_color TEXT, interior_color TEXT,
            canonical_identity TEXT NOT NULL, source_refs TEXT, quality_status TEXT NOT NULL DEFAULT 'ok',
            status TEXT NOT NULL DEFAULT 'active', lineage_metadata TEXT, correction_of TEXT,
            created_at TEXT NOT NULL, corrected_at TEXT, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TRIGGER sellable_combination_no_delete BEFORE DELETE ON sellable_combination
            BEGIN SELECT RAISE(ABORT, 'sellable_combination history is preserved'); END;
        CREATE TABLE sellable_combination_alias (
            id TEXT PRIMARY KEY, combination_id TEXT NOT NULL REFERENCES sellable_combination(id),
            alias_type TEXT NOT NULL, alias_value TEXT NOT NULL, store_scope TEXT, source_ref TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE combination_lineage (
            id TEXT PRIMARY KEY, from_combination_id TEXT NOT NULL, to_combination_id TEXT NOT NULL,
            relationship TEXT NOT NULL, comparability TEXT, approved_rule_ref TEXT, evidence_refs TEXT,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
        );
        -- Supply projections derived from accepted current-state facts (append-preserving).
        CREATE TABLE current_supply_projection (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, combination_id TEXT, store_scope TEXT NOT NULL,
            availability_state TEXT NOT NULL, arrival_date TEXT, available_for_retail_date TEXT, age_days INTEGER,
            source_state_refs TEXT, fact_refs TEXT, retail_eligible INTEGER NOT NULL DEFAULT 0, exclusion_reason TEXT,
            quality_status TEXT, confidence TEXT, calculation_timestamp TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'current'
        );
        CREATE TABLE future_supply_projection (
            id TEXT PRIMARY KEY, production_order_id TEXT, combination_id TEXT, store_scope TEXT NOT NULL,
            production_state TEXT, eta_start TEXT, eta_end TEXT, arrival_month TEXT, timing_confidence TEXT,
            editability TEXT, cancellation_status TEXT, source_refs TEXT, fact_refs TEXT, identity_linkage TEXT,
            quality_status TEXT, calculation_timestamp TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'current'
        );
        CREATE TABLE supply_commitment (
            id TEXT PRIMARY KEY, unit_or_order_id TEXT, unit_identity_kind TEXT, combination_id TEXT,
            store_scope TEXT NOT NULL, commitment_type TEXT NOT NULL, decision_ref TEXT, approval_time TEXT,
            expected_supply_timing TEXT, arrival_month TEXT, lifecycle_status TEXT NOT NULL DEFAULT 'proposed',
            commitment_source TEXT, supersedes TEXT, superseded_by TEXT, cancellation_status TEXT,
            fact_refs TEXT, audit_refs TEXT, created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        -- Historical retail projection (accepted Business Facts only; append-preserving).
        CREATE TABLE retail_history_projection (
            id TEXT PRIMARY KEY, retail_event_ref TEXT, vehicle_unit_id TEXT, combination_id TEXT,
            store_scope TEXT NOT NULL, retail_date TEXT, retail_month TEXT, arrival_refs TEXT, availability_refs TEXT,
            model_year TEXT, source_refs TEXT, fact_refs TEXT, quality_status TEXT, status TEXT NOT NULL DEFAULT 'current',
            correction_of TEXT, created_at TEXT NOT NULL
        );
        -- Availability reconstruction (month/day-aware exposure + states).
        CREATE TABLE availability_interval (
            id TEXT PRIMARY KEY, combination_id TEXT, store_scope TEXT NOT NULL, bucket TEXT, period_start TEXT,
            period_end TEXT, available_state TEXT NOT NULL, available_unit_days REAL, opening_depth INTEGER,
            closing_depth INTEGER, arrivals INTEGER, retail_events INTEGER, stockout_periods TEXT, source_refs TEXT,
            fact_refs TEXT, quality_status TEXT, confidence TEXT, unresolved_gaps TEXT, created_at TEXT NOT NULL
        );
        -- Issued Demand baseline (append-preserving; reproducibility-pinned).
        CREATE TABLE demand_result (
            id TEXT PRIMARY KEY, combination_id TEXT, store_scope TEXT NOT NULL, horizon_start TEXT, horizon_end TEXT,
            monthly_expected TEXT, baseline_evidence TEXT, evidence_tier TEXT, direct_evidence INTEGER,
            availability_adjustment TEXT, seasonality_ref TEXT, trend_ref TEXT, confidence TEXT, uncertainty TEXT,
            policy_versions TEXT, calculation_version TEXT, source_refs TEXT, fact_refs TEXT, reproducibility_package TEXT,
            scenario_id TEXT, issued_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER demand_result_no_delete BEFORE DELETE ON demand_result
            BEGIN SELECT RAISE(ABORT, 'demand_result issued history is preserved'); END;
        -- Month-by-month forecast (issued).
        CREATE TABLE forecast_result (
            id TEXT PRIMARY KEY, combination_id TEXT, store_scope TEXT NOT NULL, issue_date TEXT NOT NULL,
            horizon_start TEXT, horizon_end TEXT, total_expected REAL, confidence TEXT, input_state_refs TEXT,
            policy_versions TEXT, calculation_version TEXT, lineage_refs TEXT, scenario_id TEXT,
            reproducibility_package TEXT, demand_result_id TEXT, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER forecast_result_no_delete BEFORE DELETE ON forecast_result
            BEGIN SELECT RAISE(ABORT, 'forecast_result issued history is preserved'); END;
        CREATE TABLE forecast_month (
            id TEXT PRIMARY KEY, forecast_id TEXT NOT NULL REFERENCES forecast_result(id), month TEXT NOT NULL,
            expected_retail REAL, cumulative_expected REAL, confidence TEXT, seq INTEGER
        );
        -- Desired ending coverage resolution (resolved through Phase 3 policy).
        CREATE TABLE desired_coverage_resolution (
            id TEXT PRIMARY KEY, combination_id TEXT, store_scope TEXT NOT NULL, policy_version TEXT, scope TEXT,
            effective_period TEXT, unit_contract TEXT, resolved_value TEXT, resolution_status TEXT NOT NULL,
            fallback_used INTEGER NOT NULL DEFAULT 0, note TEXT, created_at TEXT NOT NULL
        );
        -- Inventory plan (Need/Excess; issued).
        CREATE TABLE inventory_plan_result (
            id TEXT PRIMARY KEY, combination_id TEXT, store_scope TEXT NOT NULL, evaluated_start TEXT, evaluated_end TEXT,
            expected_demand REAL, current_supply INTEGER, future_supply INTEGER, committed_supply INTEGER,
            qualifying_supply INTEGER, desired_ending_coverage TEXT, need REAL, excess REAL, planning_state TEXT NOT NULL,
            confidence TEXT, evidence TEXT, policy_versions TEXT, calculation_version TEXT, reproducibility_package TEXT,
            demand_result_id TEXT, scenario_id TEXT, issued_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER inventory_plan_result_no_delete BEFORE DELETE ON inventory_plan_result
            BEGIN SELECT RAISE(ABORT, 'inventory_plan_result issued history is preserved'); END;
        CREATE TABLE inventory_plan_month (
            id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES inventory_plan_result(id), month TEXT NOT NULL,
            expected_demand REAL, cumulative_demand REAL, cumulative_supply INTEGER, shortage REAL, excess REAL,
            confidence TEXT, seq INTEGER
        );
        -- Portfolio aggregation (model / model-year / portfolio).
        CREATE TABLE portfolio_plan_result (
            id TEXT PRIMARY KEY, store_scope TEXT NOT NULL, evaluated_start TEXT, evaluated_end TEXT, level TEXT NOT NULL,
            grouping_key TEXT, summary TEXT, plan_refs TEXT, monthly_demand TEXT, supply_by_state TEXT, need REAL,
            excess REAL, unresolved_quantity REAL, confidence TEXT, timing_risk TEXT, calculation_version TEXT,
            issued_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER portfolio_plan_result_no_delete BEFORE DELETE ON portfolio_plan_result
            BEGIN SELECT RAISE(ABORT, 'portfolio_plan_result issued history is preserved'); END;
        -- Issued planning output reference index (append-preserving).
        CREATE TABLE issued_planning_output (
            id TEXT PRIMARY KEY, output_type TEXT NOT NULL, output_id TEXT NOT NULL, combination_id TEXT,
            store_scope TEXT, calculation_version TEXT, reproducibility_package TEXT, scenario_id TEXT,
            issued_time TEXT NOT NULL
        );
        CREATE TRIGGER issued_planning_output_no_delete BEFORE DELETE ON issued_planning_output
            BEGIN SELECT RAISE(ABORT, 'issued_planning_output history is preserved'); END;
    """),
    (5, "production_supply_workflows", """
        -- Production pipeline projection (from accepted Production Orders + Business Facts).
        CREATE TABLE production_pipeline_projection (
            id TEXT PRIMARY KEY, production_order_id TEXT, combination_id TEXT, store_scope TEXT NOT NULL,
            order_status TEXT, production_status TEXT, allocation_status TEXT, vin_status TEXT,
            build_timing TEXT, shipment_timing TEXT, eta_start TEXT, eta_end TEXT, arrival_month TEXT,
            source_refs TEXT, fact_refs TEXT, identity_refs TEXT, quality_status TEXT, confidence TEXT,
            status TEXT NOT NULL DEFAULT 'current', conflict TEXT, recorded_time TEXT NOT NULL, effective_time TEXT
        );
        CREATE TRIGGER production_pipeline_no_delete BEFORE DELETE ON production_pipeline_projection
            BEGIN SELECT RAISE(ABORT, 'production_pipeline history is preserved'); END;
        CREATE TABLE eta_history (
            id TEXT PRIMARY KEY, production_order_id TEXT, pipeline_id TEXT, precision TEXT NOT NULL,
            eta_start TEXT, eta_end TEXT, arrival_month TEXT, confidence TEXT, stale INTEGER NOT NULL DEFAULT 0,
            conflicting INTEGER NOT NULL DEFAULT 0, supersedes TEXT, source_refs TEXT, recorded_time TEXT NOT NULL
        );
        CREATE TRIGGER eta_history_no_delete BEFORE DELETE ON eta_history
            BEGIN SELECT RAISE(ABORT, 'eta_history is preserved'); END;
        CREATE TABLE editability_result (
            id TEXT PRIMARY KEY, production_order_id TEXT, store_scope TEXT, editability_state TEXT NOT NULL,
            editable_dimensions TEXT, cutoff TEXT, source_refs TEXT, policy_refs TEXT, confidence TEXT,
            unresolved_conditions TEXT, recorded_time TEXT NOT NULL
        );
        CREATE TABLE model_year_transition_result (
            id TEXT PRIMARY KEY, store_scope TEXT, model TEXT, outgoing_model_year TEXT, incoming_model_year TEXT,
            overlap TEXT, lineage_status TEXT, transition_window TEXT, arrival_risk TEXT, constrained_incoming INTEGER,
            evidence TEXT, policy_refs TEXT, confidence TEXT, recorded_time TEXT NOT NULL
        );
        CREATE TABLE incoming_risk_result (
            id TEXT PRIMARY KEY, subject_kind TEXT, subject_ref TEXT, combination_id TEXT, store_scope TEXT,
            classification TEXT NOT NULL, reasons TEXT, timing TEXT, affected_need_window TEXT, source_facts TEXT,
            policy_versions TEXT, calculation_version TEXT, confidence TEXT, reproducibility_package TEXT,
            issued_time TEXT NOT NULL
        );
        CREATE TRIGGER incoming_risk_no_delete BEFORE DELETE ON incoming_risk_result
            BEGIN SELECT RAISE(ABORT, 'incoming_risk_result is preserved'); END;
        -- Governed supply workflows (common lifecycle) + transitions + evidence.
        CREATE TABLE supply_workflow (
            id TEXT PRIMARY KEY, workflow_type TEXT NOT NULL, subject_identity TEXT, subject_kind TEXT,
            combination_id TEXT, store_scope TEXT NOT NULL, target_month TEXT, quantity INTEGER NOT NULL DEFAULT 1,
            originating_need_ref TEXT, qualifying_supply_at_propose INTEGER, expected_resulting_supply TEXT,
            proposal_reason TEXT, evidence TEXT, policy_versions TEXT, calculation_version TEXT, approval_decision TEXT,
            execution_refs TEXT, lifecycle_status TEXT NOT NULL DEFAULT 'DRAFT', idempotency_identity TEXT,
            audit_refs TEXT, reproducibility_package TEXT, scenario_id TEXT, created_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TRIGGER supply_workflow_no_delete BEFORE DELETE ON supply_workflow
            BEGIN SELECT RAISE(ABORT, 'supply_workflow history is preserved'); END;
        CREATE TABLE supply_workflow_transition (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES supply_workflow(id), from_status TEXT,
            to_status TEXT NOT NULL, actor TEXT, action TEXT, reconciliation_ref TEXT, audit_ref TEXT,
            detail TEXT, at TEXT NOT NULL
        );
        CREATE TRIGGER supply_workflow_transition_no_delete BEFORE DELETE ON supply_workflow_transition
            BEGIN SELECT RAISE(ABORT, 'supply_workflow_transition is preserved'); END;
        CREATE TABLE supply_workflow_evidence (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, evidence_kind TEXT, ref TEXT, detail TEXT,
            recorded_at TEXT NOT NULL
        );
        -- Domain action detail tables.
        CREATE TABLE cpo_action (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, production_order_id TEXT, allocation_ref TEXT,
            combination_id TEXT, discrete_quantity INTEGER, arrival_month TEXT, commitment_ref TEXT,
            completion_ref TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE ppo_action (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, order_or_unit_id TEXT, allocation_evidence TEXT,
            combination_id TEXT, discrete_quantity INTEGER, arrival_month TEXT, commitment_ref TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE dealer_trade_action (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, direction TEXT, counterparty TEXT, unit_identity TEXT,
            combination_id TEXT, arrival_month TEXT, received_vehicle_unit_id TEXT, commitment_ref TEXT,
            completion_ref TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE dealer_trade_status_history (
            id TEXT PRIMARY KEY, dealer_trade_id TEXT NOT NULL, status TEXT NOT NULL, actor TEXT, reason TEXT,
            at TEXT NOT NULL
        );
        CREATE TABLE ctp_action (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, production_order_id TEXT, original_combination_id TEXT,
            proposed_combination_id TEXT, editability_ref TEXT, cutoff TEXT, originating_need_ref TEXT,
            originating_excess_ref TEXT, expected_portfolio_effect TEXT, resulting_order_state TEXT,
            superseded_future_supply TEXT, new_future_supply TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE ctp_change_detail (
            id TEXT PRIMARY KEY, ctp_id TEXT NOT NULL, dimension TEXT, from_value TEXT, to_value TEXT,
            accepted INTEGER, at TEXT NOT NULL
        );
        -- Deterministic commitment reconciliation results.
        CREATE TABLE commitment_reconciliation_result (
            id TEXT PRIMARY KEY, workflow_id TEXT, transition_ref TEXT, outcome TEXT NOT NULL, subject_identity TEXT,
            combination_id TEXT, supply_ref TEXT, prior_qualifying INTEGER, new_qualifying INTEGER, detail TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TRIGGER commitment_reconciliation_no_delete BEFORE DELETE ON commitment_reconciliation_result
            BEGIN SELECT RAISE(ABORT, 'commitment_reconciliation_result is preserved'); END;
        -- Sequential recomputation runs + steps (each intermediate state preserved).
        CREATE TABLE sequential_planning_run (
            id TEXT PRIMARY KEY, store_scope TEXT NOT NULL, base_portfolio_ref TEXT, status TEXT NOT NULL,
            calculation_version TEXT, scenario_id TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE sequential_planning_step (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES sequential_planning_run(id), seq INTEGER,
            action_ref TEXT, combination_id TEXT, causing_action TEXT, plan_ref TEXT, need_before REAL, need_after REAL,
            excess_after REAL, suppressed INTEGER NOT NULL DEFAULT 0, outcome TEXT, at TEXT NOT NULL
        );
        CREATE TRIGGER sequential_planning_step_no_delete BEFORE DELETE ON sequential_planning_step
            BEGIN SELECT RAISE(ABORT, 'sequential_planning_step is preserved'); END;
        -- Workflow-triggered issued planning output references + execution confirmations.
        CREATE TABLE workflow_issued_output_reference (
            id TEXT PRIMARY KEY, workflow_id TEXT, causing_action TEXT, output_type TEXT, output_id TEXT,
            combination_id TEXT, store_scope TEXT, calculation_version TEXT, scenario_id TEXT, issued_time TEXT NOT NULL
        );
        CREATE TRIGGER workflow_issued_output_no_delete BEFORE DELETE ON workflow_issued_output_reference
            BEGIN SELECT RAISE(ABORT, 'workflow_issued_output_reference is preserved'); END;
        CREATE TABLE execution_confirmation (
            id TEXT PRIMARY KEY, workflow_id TEXT, confirmation_kind TEXT, subject_identity TEXT, resulting_supply_ref TEXT,
            outcome TEXT, detail TEXT, confirmed_at TEXT NOT NULL
        );
    """),
    (6, "service_loaner", """
        -- Service Loaner Unit — a Vehicle Unit's Service Loaner participation (does NOT replace
        -- Vehicle Unit identity).
        CREATE TABLE service_loaner_unit (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, vin TEXT, store_scope TEXT NOT NULL, combination_id TEXT,
            membership_state TEXT NOT NULL DEFAULT 'CANDIDATE', accepted_in_service_date TEXT,
            in_service_date_authority TEXT, current_rental_state TEXT, last_checkout_mileage TEXT,
            last_accepted_snapshot TEXT, active_fleet_presence INTEGER NOT NULL DEFAULT 0, entry_decision TEXT,
            entry_execution_event TEXT, retirement_decision TEXT, return_confirmation TEXT, retirement_event TEXT,
            used_cars_receipt TEXT, return_to_retail_ref TEXT, correction_of TEXT, superseded_by TEXT,
            quality_status TEXT, confidence TEXT, created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TRIGGER service_loaner_unit_no_delete BEFORE DELETE ON service_loaner_unit
            BEGIN SELECT RAISE(ABORT, 'service_loaner_unit history is preserved'); END;
        CREATE TABLE service_loaner_membership_history (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
            actor TEXT, action TEXT, reconciliation_ref TEXT, audit_ref TEXT, detail TEXT, at TEXT NOT NULL
        );
        CREATE TRIGGER service_loaner_membership_history_no_delete BEFORE DELETE ON service_loaner_membership_history
            BEGIN SELECT RAISE(ABORT, 'service_loaner_membership_history is preserved'); END;
        CREATE TABLE service_loaner_snapshot_reconciliation (
            id TEXT PRIMARY KEY, import_batch_id TEXT, snapshot_type TEXT, store_scope TEXT, vin TEXT,
            service_loaner_unit_id TEXT, outcome TEXT NOT NULL, reason TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_operational_state (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, snapshot_ref TEXT, rental_state TEXT,
            availability_state TEXT, conflict TEXT, source_refs TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_in_service_date_resolution (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, candidate_values TEXT, source TEXT, evidence TEXT,
            authority_level TEXT, effective_time TEXT, accepted_value TEXT, conflict_state TEXT, correction_of TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_checkout_mileage_fact (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, value_kind TEXT NOT NULL, value INTEGER,
            snapshot_ref TEXT, source TEXT, provenance TEXT, status TEXT NOT NULL DEFAULT 'current', supersedes TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_monitoring_alert (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, rule TEXT NOT NULL, prompt TEXT, status TEXT NOT NULL,
            snapshot_ref TEXT, in_service_date TEXT, elapsed_days INTEGER, threshold_days INTEGER, policy_refs TEXT,
            cleared_reason TEXT, created_at TEXT NOT NULL, cleared_at TEXT
        );
        CREATE TRIGGER service_loaner_monitoring_alert_no_delete BEFORE DELETE ON service_loaner_monitoring_alert
            BEGIN SELECT RAISE(ABORT, 'service_loaner_monitoring_alert history is preserved'); END;
        CREATE TABLE service_loaner_entry_candidate (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, combination_id TEXT, store_scope TEXT, eligibility TEXT,
            eligibility_reasons TEXT, availability TEXT, new_retail_opportunity_cost TEXT, actual_state TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_portfolio_plan (
            id TEXT PRIMARY KEY, store_scope TEXT NOT NULL, required_quantity INTEGER, current_active INTEGER,
            selected TEXT, sacrifices TEXT, need_basis TEXT, policy_versions TEXT, calculation_version TEXT,
            scenario_id TEXT, issued_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER service_loaner_portfolio_plan_no_delete BEFORE DELETE ON service_loaner_portfolio_plan
            BEGIN SELECT RAISE(ABORT, 'service_loaner_portfolio_plan is preserved'); END;
        CREATE TABLE service_loaner_economic_result (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, store_scope TEXT, decision_point TEXT,
            alternatives TEXT, economic_call TEXT, assumptions TEXT, uncertainty TEXT, resolution_status TEXT NOT NULL,
            policy_versions TEXT, calculation_version TEXT, fact_refs TEXT, reproducibility_package TEXT, scenario_id TEXT,
            issued_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER service_loaner_economic_result_no_delete BEFORE DELETE ON service_loaner_economic_result
            BEGIN SELECT RAISE(ABORT, 'service_loaner_economic_result issued history is preserved'); END;
        CREATE TABLE service_loaner_execution_status (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, economic_result_id TEXT, status TEXT NOT NULL,
            reason TEXT, blocking_factors TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_retirement_eligibility (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, eligible INTEGER, reasons TEXT, policy_versions TEXT,
            tenure_days INTEGER, recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_retirement_action (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, store_scope TEXT, lifecycle_status TEXT NOT NULL,
            economic_result_id TEXT, decision_ref TEXT, approval_time TEXT, provisional INTEGER NOT NULL DEFAULT 0,
            cancellation_status TEXT, correction_of TEXT, created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE service_loaner_return_confirmation (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, retirement_action_id TEXT, actual_event_ref TEXT,
            confirmed_by TEXT, confirmed_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_retirement_event (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, retirement_action_id TEXT, return_confirmation_id TEXT,
            store_scope TEXT, membership_reconciled INTEGER, event_time TEXT NOT NULL
        );
        CREATE TRIGGER service_loaner_retirement_event_no_delete BEFORE DELETE ON service_loaner_retirement_event
            BEGIN SELECT RAISE(ABORT, 'service_loaner_retirement_event is preserved'); END;
        -- Used Cars receipt — a single idempotent confirmation, immutable, no checklist.
        CREATE TABLE used_cars_receipt (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, vehicle_unit_id TEXT, retirement_event_ref TEXT,
            store_scope TEXT, confirming_principal TEXT, correlation_id TEXT, audit_ref TEXT, confirmed_at TEXT NOT NULL,
            UNIQUE(service_loaner_unit_id)
        );
        CREATE TRIGGER used_cars_receipt_no_update BEFORE UPDATE ON used_cars_receipt
            BEGIN SELECT RAISE(ABORT, 'used_cars_receipt is immutable'); END;
        CREATE TRIGGER used_cars_receipt_no_delete BEFORE DELETE ON used_cars_receipt
            BEGIN SELECT RAISE(ABORT, 'used_cars_receipt is preserved'); END;
        CREATE TABLE service_loaner_reconciliation_result (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, vehicle_unit_id TEXT, store_scope TEXT, outcome TEXT NOT NULL,
            supply_ref TEXT, detail TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TRIGGER service_loaner_reconciliation_result_no_delete BEFORE DELETE ON service_loaner_reconciliation_result
            BEGIN SELECT RAISE(ABORT, 'service_loaner_reconciliation_result is preserved'); END;
        CREATE TABLE service_loaner_scenario_result (
            id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, store_scope TEXT, kind TEXT, overrides TEXT, output TEXT,
            baseline_ref TEXT, issued_time TEXT NOT NULL
        );
        CREATE TABLE service_loaner_resale_reference (
            id TEXT PRIMARY KEY, service_loaner_unit_id TEXT, retirement_event_ref TEXT, used_cars_receipt_ref TEXT,
            resale_event_ref TEXT, resale_timing TEXT, resale_value TEXT, predicted_ref TEXT, observed_ref TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE service_loaner_issued_output (
            id TEXT PRIMARY KEY, output_type TEXT NOT NULL, output_id TEXT NOT NULL, service_loaner_unit_id TEXT,
            store_scope TEXT, calculation_version TEXT, scenario_id TEXT, issued_time TEXT NOT NULL
        );
        CREATE TRIGGER service_loaner_issued_output_no_delete BEFORE DELETE ON service_loaner_issued_output
            BEGIN SELECT RAISE(ABORT, 'service_loaner_issued_output is preserved'); END;
    """),
    (7, "executive_demo", """
        -- Executive Demo Unit — a Vehicle Unit's Executive Demo participation (does NOT replace
        -- Vehicle Unit identity). A SEPARATE domain from Service Loaner (own records).
        CREATE TABLE executive_demo_unit (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, vin TEXT, store_scope TEXT NOT NULL, combination_id TEXT,
            membership_state TEXT NOT NULL DEFAULT 'CANDIDATE', designation_decision TEXT, designation_execution_event TEXT,
            active_date TEXT, in_service_or_activation_date TEXT, current_mileage TEXT, assigned_role TEXT,
            model_preference_evidence TEXT, portfolio_role TEXT, retirement_decision TEXT, retirement_event TEXT,
            return_to_retail_event TEXT, used_cars_receipt TEXT, current_economic_result TEXT,
            active_fleet_supply_ref TEXT, correction_of TEXT, superseded_by TEXT, quality_status TEXT, confidence TEXT,
            created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TRIGGER executive_demo_unit_no_delete BEFORE DELETE ON executive_demo_unit
            BEGIN SELECT RAISE(ABORT, 'executive_demo_unit history is preserved'); END;
        CREATE TABLE executive_demo_membership_history (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
            actor TEXT, action TEXT, reconciliation_ref TEXT, audit_ref TEXT, detail TEXT, at TEXT NOT NULL
        );
        CREATE TRIGGER executive_demo_membership_history_no_delete BEFORE DELETE ON executive_demo_membership_history
            BEGIN SELECT RAISE(ABORT, 'executive_demo_membership_history is preserved'); END;
        CREATE TABLE executive_demo_portfolio_requirement (
            id TEXT PRIMARY KEY, store_scope TEXT NOT NULL, required_size INTEGER, model_representation TEXT,
            model_preference_ref TEXT, policy_versions TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_portfolio_plan (
            id TEXT PRIMARY KEY, store_scope TEXT NOT NULL, required_size INTEGER, current_active INTEGER,
            committed INTEGER, need INTEGER, selected TEXT, tradeoffs TEXT, sacrifices TEXT, best_overall TEXT,
            need_basis TEXT, policy_versions TEXT, calculation_version TEXT, scenario_id TEXT, issued_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER executive_demo_portfolio_plan_no_delete BEFORE DELETE ON executive_demo_portfolio_plan
            BEGIN SELECT RAISE(ABORT, 'executive_demo_portfolio_plan is preserved'); END;
        CREATE TABLE executive_demo_candidate (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, combination_id TEXT, store_scope TEXT, model TEXT, model_year TEXT,
            age_days INTEGER, mileage TEXT, eligibility TEXT, new_retail_refs TEXT, opportunity_cost_ref TEXT,
            expected_value TEXT, expected_lifecycle_ref TEXT, policy_versions TEXT, calculation_version TEXT,
            source_refs TEXT, quality_status TEXT, confidence TEXT, scenario_id TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_eligibility_result (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, combination_id TEXT, store_scope TEXT, outcome TEXT NOT NULL,
            reasons TEXT, policy_versions TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_model_preference_resolution (
            id TEXT PRIMARY KEY, store_scope TEXT, resolution_status TEXT NOT NULL, preferred TEXT, hierarchy TEXT,
            substitutions TEXT, policy_version TEXT, scope TEXT, note TEXT, scenario_id TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_opportunity_cost_result (
            id TEXT PRIMARY KEY, vehicle_unit_id TEXT, combination_id TEXT, store_scope TEXT, affected_months TEXT,
            plan_position TEXT, cost_value TEXT, expected_return_path TEXT, confidence TEXT, policy_versions TEXT,
            calculation_version TEXT, plan_refs TEXT, reproducibility_package TEXT, scenario_id TEXT, issued_time TEXT NOT NULL
        );
        CREATE TRIGGER executive_demo_opportunity_cost_no_delete BEFORE DELETE ON executive_demo_opportunity_cost_result
            BEGIN SELECT RAISE(ABORT, 'executive_demo_opportunity_cost_result is preserved'); END;
        CREATE TABLE executive_demo_lifecycle_projection (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, candidate_id TEXT, store_scope TEXT, activation_timing TEXT,
            expected_duration TEXT, expected_mileage TEXT, expected_depreciation TEXT, expected_retirement_timing TEXT,
            expected_return_path TEXT, assumptions TEXT, uncertainty TEXT, resolution_status TEXT NOT NULL,
            policy_versions TEXT, calculation_version TEXT, issued_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER executive_demo_lifecycle_projection_no_delete BEFORE DELETE ON executive_demo_lifecycle_projection
            BEGIN SELECT RAISE(ABORT, 'executive_demo_lifecycle_projection is preserved'); END;
        CREATE TABLE executive_demo_economic_result (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, candidate_id TEXT, store_scope TEXT, decision_point TEXT,
            alternatives TEXT, economic_call TEXT, opportunity_cost_ref TEXT, expected_benefit TEXT, retirement_impact TEXT,
            assumptions TEXT, uncertainty TEXT, resolution_status TEXT NOT NULL, policy_versions TEXT,
            calculation_version TEXT, fact_refs TEXT, reproducibility_package TEXT, scenario_id TEXT, issued_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'issued'
        );
        CREATE TRIGGER executive_demo_economic_result_no_delete BEFORE DELETE ON executive_demo_economic_result
            BEGIN SELECT RAISE(ABORT, 'executive_demo_economic_result issued history is preserved'); END;
        CREATE TABLE executive_demo_execution_status (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, economic_result_id TEXT, status TEXT NOT NULL, reason TEXT,
            blocking_factors TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_designation_action (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, store_scope TEXT, lifecycle_status TEXT NOT NULL,
            candidate_id TEXT, economic_result_id TEXT, decision_ref TEXT, approval_time TEXT, cancellation_status TEXT,
            correction_of TEXT, created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE executive_demo_retirement_eligibility (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, eligible INTEGER, reasons TEXT, policy_versions TEXT,
            tenure_days INTEGER, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_retirement_action (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, store_scope TEXT, lifecycle_status TEXT NOT NULL,
            economic_result_id TEXT, decision_ref TEXT, approval_time TEXT, cancellation_status TEXT, correction_of TEXT,
            created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE executive_demo_retirement_event (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, retirement_action_id TEXT, store_scope TEXT,
            membership_reconciled INTEGER, event_time TEXT NOT NULL
        );
        CREATE TRIGGER executive_demo_retirement_event_no_delete BEFORE DELETE ON executive_demo_retirement_event
            BEGIN SELECT RAISE(ABORT, 'executive_demo_retirement_event is preserved'); END;
        CREATE TABLE executive_demo_return_to_retail_event (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, retirement_event_ref TEXT, store_scope TEXT,
            restored_supply_ref TEXT, confirmed_by TEXT, confirmed_at TEXT NOT NULL
        );
        -- Used Cars receipt — separate record from Service Loaner; single idempotent, immutable.
        CREATE TABLE executive_demo_used_cars_receipt (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, vehicle_unit_id TEXT, retirement_event_ref TEXT,
            store_scope TEXT, confirming_principal TEXT, correlation_id TEXT, audit_ref TEXT, confirmed_at TEXT NOT NULL,
            UNIQUE(executive_demo_unit_id)
        );
        CREATE TRIGGER executive_demo_used_cars_receipt_no_update BEFORE UPDATE ON executive_demo_used_cars_receipt
            BEGIN SELECT RAISE(ABORT, 'executive_demo_used_cars_receipt is immutable'); END;
        CREATE TRIGGER executive_demo_used_cars_receipt_no_delete BEFORE DELETE ON executive_demo_used_cars_receipt
            BEGIN SELECT RAISE(ABORT, 'executive_demo_used_cars_receipt is preserved'); END;
        CREATE TABLE executive_demo_reconciliation_result (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, vehicle_unit_id TEXT, store_scope TEXT, outcome TEXT NOT NULL,
            supply_ref TEXT, detail TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TRIGGER executive_demo_reconciliation_result_no_delete BEFORE DELETE ON executive_demo_reconciliation_result
            BEGIN SELECT RAISE(ABORT, 'executive_demo_reconciliation_result is preserved'); END;
        CREATE TABLE executive_demo_scenario_result (
            id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, store_scope TEXT, kind TEXT, overrides TEXT, output TEXT,
            baseline_ref TEXT, issued_time TEXT NOT NULL
        );
        CREATE TABLE executive_demo_resale_reference (
            id TEXT PRIMARY KEY, executive_demo_unit_id TEXT, designation_ref TEXT, retirement_event_ref TEXT,
            return_path TEXT, used_cars_receipt_ref TEXT, resale_event_ref TEXT, resale_value TEXT, predicted_ref TEXT,
            observed_ref TEXT, recorded_at TEXT NOT NULL
        );
        CREATE TABLE executive_demo_issued_output (
            id TEXT PRIMARY KEY, output_type TEXT NOT NULL, output_id TEXT NOT NULL, executive_demo_unit_id TEXT,
            store_scope TEXT, calculation_version TEXT, scenario_id TEXT, issued_time TEXT NOT NULL
        );
        CREATE TRIGGER executive_demo_issued_output_no_delete BEFORE DELETE ON executive_demo_issued_output
            BEGIN SELECT RAISE(ABORT, 'executive_demo_issued_output is preserved'); END;
    """),
]


def _ensure_migration_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migration_record (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );""")


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_migration_table(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM migration_record").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def migrate(conn: sqlite3.Connection, clock) -> int:
    """Apply pending migrations in order. Returns the resulting version. Each
    migration + its record commit atomically; a failure aborts without partial state."""
    _ensure_migration_table(conn)
    applied_to = current_version(conn)
    for version, name, sql in MIGRATIONS:
        if version <= applied_to:
            continue
        if version != applied_to + 1:
            raise MigrationError(
                message="Migration sequence is broken.",
                technical_detail=f"expected {applied_to + 1}, found {version}")
        try:
            with conn:  # atomic
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO migration_record(version, name, applied_at) VALUES(?,?,?)",
                    (version, name, clock.now().isoformat()))
            applied_to = version
        except sqlite3.Error as e:
            raise MigrationError(message="A schema migration failed.",
                                 technical_detail=f"{name}: {e}")
    return applied_to


class Db:
    """Thin owner of a connection + migration state. Repositories take this."""

    def __init__(self, path: str, clock):
        self.path = path
        self.clock = clock
        self.conn = connect(path)

    def migrate(self) -> int:
        return migrate(self.conn, self.clock)

    def version(self) -> int:
        return current_version(self.conn)

    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error as e:
            raise PersistenceError(technical_detail=str(e))
