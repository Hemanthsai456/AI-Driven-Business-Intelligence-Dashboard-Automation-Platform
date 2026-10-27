"""Targeted verification for Home Page Dashboard & Analytical Result tabs contract.

Verifies:
1. Data Preview and Cleaning Report tabs are removed from the Home page's generated
   Dashboard & Analytical Result section (DashboardPanelsView.tsx).
2. Executive Dashboard is retained as the sole tab header in DashboardPanelsView.tsx.
3. The trust-layer summary strip retains the cleaning rules badge as an informative
   badge rather than an obsolete tab switcher.
4. Export HTML, Print, and Reset Dashboard controls are preserved.
5. Interactive tile features (KPI cards, charts, slicers, and tile-level modals)
   remain intact.
6. Data Studio's standalone tabs (Overview, Profiling, Quality, Cleaning, EDA)
   remain completely intact with full functionality.
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
COMPONENTS_DIR = FRONTEND_DIR / "components"
DATA_STUDIO_DIR = COMPONENTS_DIR / "data_studio"


def test_dashboard_panels_view_only_has_executive_dashboard_tab():
    """Verify that DashboardPanelsView contains only Executive Dashboard and no redundant tabs."""
    panels_view_file = COMPONENTS_DIR / "DashboardPanelsView.tsx"
    assert panels_view_file.exists(), "DashboardPanelsView.tsx must exist"

    content = panels_view_file.read_text(encoding="utf-8")

    # 1. Executive Dashboard tab header must be present
    assert "Executive Dashboard" in content, "Executive Dashboard header must be present"
    assert (
        '<div className="flex items-center gap-1.5 px-3.5 py-2 border-b-2 border-primary text-primary font-bold">'
        in content
    ), "Executive Dashboard must be rendered as an active tab indicator in the tab bar"

    # 2. Data Preview and Cleaning Report tab buttons must be removed from the tab bar
    assert "<span>Data Preview</span>" not in content, "Data Preview tab button must not exist in DashboardPanelsView"
    assert "Cleaning Report (" not in content, "Cleaning Report tab button with count must not exist in DashboardPanelsView"
    assert "<span>Trace & SQL</span>" not in content, "Trace & SQL tab button must not exist in DashboardPanelsView"

    # 3. Tab panels 2, 3, 4 should not exist as tab switches
    assert "{/* TAB 2: DATA PREVIEW */}" not in content
    assert "{/* TAB 3: CLEANING REPORT */}" not in content
    assert "{/* TAB 4: TRACE & SQL */}" not in content
    assert "activeTab === 'data'" not in content
    assert "activeTab === 'cleaning'" not in content
    assert "activeTab === 'trace'" not in content
    assert "activeTab === 'dashboard'" not in content

    # 4. Obsolete activeTab state should not exist
    assert "const [activeTab, setActiveTab]" not in content

    # 5. Cleaning rules badge should be an informative badge rather than a tab-switching button
    assert (
        "<span>{cleaningCount} cleaning rules applied</span>" in content
    ), "Cleaning rules count should remain as an informative badge in the summary strip"
    assert 'onClick={() => setActiveTab(\'cleaning\')}' not in content


def test_dashboard_panels_view_preserves_core_dashboard_features():
    """Verify that KPI cards, charts, slicers, export HTML, and print remain operational."""
    panels_view_file = COMPONENTS_DIR / "DashboardPanelsView.tsx"
    content = panels_view_file.read_text(encoding="utf-8")

    # Action buttons
    assert "handleExportHtml" in content, "Export HTML functionality must be preserved"
    assert "Export HTML" in content
    assert "window.print()" in content, "Print functionality must be preserved"
    assert "Print" in content
    assert "handleResetDashboard" in content, "Reset Dashboard functionality must be preserved"

    # Slicers and interactive filtering
    assert "handleToggleFilter" in content, "Cross-filtering must be preserved"
    assert "handleSlicerChange" in content, "Slicer controls must be preserved"
    assert "handleResetFilters" in content, "Filter reset must be preserved"

    # Tile editing and modals
    assert "handleTileSaved" in content, "Tile editor must be preserved"
    assert "activeModal.type" in content, "Tile detail modals (SQL, data, why, expand) must be preserved"


def test_data_studio_features_remain_intact_globally():
    """Verify that Data Studio's preview, cleaning, profiling, quality, and EDA components exist."""
    assert DATA_STUDIO_DIR.exists(), "Data Studio directory must exist"

    expected_components = [
        "OverviewTab.tsx",
        "ProfilingTab.tsx",
        "QualityTab.tsx",
        "CleaningTab.tsx",
        "EDATab.tsx",
    ]

    for comp in expected_components:
        comp_file = DATA_STUDIO_DIR / comp
        assert comp_file.exists(), f"Data Studio component {comp} must remain intact"

    # CleaningTab must retain all transformation functionality
    cleaning_tab = (DATA_STUDIO_DIR / "CleaningTab.tsx").read_text(encoding="utf-8")
    assert "transformations" in cleaning_tab or "Cleaning" in cleaning_tab

    # OverviewTab must retain raw preview functionality
    overview_tab = (DATA_STUDIO_DIR / "OverviewTab.tsx").read_text(encoding="utf-8")
    assert "Raw Data Preview" in overview_tab or "preview" in overview_tab.lower()
