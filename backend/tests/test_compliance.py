"""Tests for ComplianceManager."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.compliance import (
    ComplianceCheck,
    ComplianceFramework,
    ComplianceManager,
    ComplianceStatus,
    DataProcessingRecord,
)


async def test_gdpr_assessment_returns_checks(db_session: AsyncSession):
    manager = ComplianceManager(db_session)
    checks = await manager.run_gdpr_assessment()

    assert len(checks) > 0
    assert all(isinstance(c, ComplianceCheck) for c in checks)
    assert all(c.framework == ComplianceFramework.gdpr for c in checks)


async def test_soc2_assessment_returns_checks(db_session: AsyncSession):
    manager = ComplianceManager(db_session)
    checks = await manager.run_soc2_assessment()

    assert len(checks) > 0
    assert all(isinstance(c, ComplianceCheck) for c in checks)
    assert all(c.framework == ComplianceFramework.soc2 for c in checks)


async def test_compliance_report_structure(db_session: AsyncSession):
    manager = ComplianceManager(db_session)
    report = await manager.generate_compliance_report()

    assert "generated_at" in report
    assert "frameworks" in report
    assert "overall_status" in report
    assert "summary" in report
    assert "checks" in report
    assert isinstance(report["checks"], list)


async def test_compliance_report_with_specific_frameworks(db_session: AsyncSession):
    manager = ComplianceManager(db_session)
    report = await manager.generate_compliance_report([ComplianceFramework.gdpr])

    assert report["frameworks"] == ["gdpr"]
    assert all(c["framework"] == "gdpr" for c in report["checks"])


async def test_gdpr_processing_records_non_compliant_when_empty(db_session: AsyncSession):
    manager = ComplianceManager(db_session)
    checks = await manager.run_gdpr_assessment()

    processing_check = next(c for c in checks if c.control_id == "GDPR-30")
    assert processing_check.status == ComplianceStatus.non_compliant


async def test_gdpr_processing_records_compliant_when_present(db_session: AsyncSession):
    # Add a processing record
    record = DataProcessingRecord(
        purpose="Project management",
        data_categories="Project data, task descriptions",
        data_subjects="Developers",
        retention_period="Duration of project + 1 year",
        legal_basis="Legitimate interest",
    )
    db_session.add(record)
    await db_session.commit()

    manager = ComplianceManager(db_session)
    checks = await manager.run_gdpr_assessment()

    processing_check = next(c for c in checks if c.control_id == "GDPR-30")
    assert processing_check.status == ComplianceStatus.compliant


async def test_compliance_check_to_dict():
    check = ComplianceCheck(
        control_id="TEST-1",
        framework=ComplianceFramework.gdpr,
        title="Test Check",
        status=ComplianceStatus.compliant,
        description="A test compliance check.",
        evidence="Test evidence.",
    )
    d = check.to_dict()

    assert d["control_id"] == "TEST-1"
    assert d["framework"] == "gdpr"
    assert d["status"] == "compliant"
    assert d["evidence"] == "Test evidence."


async def test_overall_status_non_compliant_when_failures(db_session: AsyncSession):
    manager = ComplianceManager(db_session)
    report = await manager.generate_compliance_report()

    # At minimum GDPR-30 should be non_compliant (no processing records)
    has_non_compliant = any(c["status"] == "non_compliant" for c in report["checks"])
    if has_non_compliant:
        assert report["overall_status"] == "non_compliant"
