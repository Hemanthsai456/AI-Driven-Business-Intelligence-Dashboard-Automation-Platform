'use client';

import React, { useState, useMemo } from 'react';
import {
  Sparkle,
  ShieldCheck,
  AlertTriangle,
  Info,
  CheckCircle2,
  Filter,
  CheckSquare,
  Square,
  ArrowRight,
  Database,
  Layers,
  HelpCircle,
  Clock,
  Sparkles,
  Zap,
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import { Button } from '../Button';
import {
  CleaningPlan,
  CleaningRecommendation,
  DatasetMetadata,
  QualityAssessment,
  SemanticProfile,
} from '../../lib/types';

interface CleaningTabProps {
  metadata: DatasetMetadata;
  cleaningPlan: CleaningPlan | null;
  semanticProfile: SemanticProfile | null;
  qualityAssessment: QualityAssessment | null;
}

type FilterStatus = 'ALL' | 'RECOMMENDED' | 'REVIEW_REQUIRED' | 'SELECTED';

export const CleaningTab: React.FC<CleaningTabProps> = ({
  metadata,
  cleaningPlan,
  semanticProfile,
  qualityAssessment,
}) => {
  // Local state for user-controlled selection overrides
  const [selections, setSelections] = useState<Record<string, boolean>>(() => {
    if (!cleaningPlan) return {};
    const initial: Record<string, boolean> = {};
    for (const rec of cleaningPlan.recommendations) {
      initial[rec.recommendation_id] = rec.default_selected;
    }
    return initial;
  });

  const [activeFilter, setActiveFilter] = useState<FilterStatus>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Update selections when cleaningPlan changes (e.g. switching datasets)
  React.useEffect(() => {
    if (!cleaningPlan) {
      setSelections({});
      return;
    }
    const initial: Record<string, boolean> = {};
    for (const rec of cleaningPlan.recommendations) {
      initial[rec.recommendation_id] = rec.default_selected;
    }
    setSelections(initial);
  }, [cleaningPlan?.dataset_id]);

  const toggleSelection = (recId: string) => {
    setSelections((prev) => ({
      ...prev,
      [recId]: !prev[recId],
    }));
  };

  const selectAllSafe = () => {
    if (!cleaningPlan) return;
    setSelections((prev) => {
      const next = { ...prev };
      for (const rec of cleaningPlan.recommendations) {
        if (rec.risk_level === 'LOW' && rec.status === 'RECOMMENDED') {
          next[rec.recommendation_id] = true;
        }
      }
      return next;
    });
  };

  const deselectAll = () => {
    if (!cleaningPlan) return;
    setSelections((prev) => {
      const next = { ...prev };
      for (const rec of cleaningPlan.recommendations) {
        next[rec.recommendation_id] = false;
      }
      return next;
    });
  };

  const allRecs = cleaningPlan?.recommendations || [];

  const selectedCount = useMemo(() => {
    return allRecs.filter((r) => selections[r.recommendation_id]).length;
  }, [allRecs, selections]);

  const filteredRecommendations = useMemo(() => {
    return allRecs.filter((rec) => {
      const isSelected = !!selections[rec.recommendation_id];

      // Status filter
      if (activeFilter === 'RECOMMENDED' && rec.status !== 'RECOMMENDED') return false;
      if (activeFilter === 'REVIEW_REQUIRED' && !rec.requires_review) return false;
      if (activeFilter === 'SELECTED' && !isSelected) return false;

      // Search query
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesCol = rec.column_name ? rec.column_name.toLowerCase().includes(query) : false;
        const matchesOp = rec.operation.toLowerCase().includes(query);
        const matchesCat = rec.category.toLowerCase().includes(query);
        const matchesRationale = rec.rationale.toLowerCase().includes(query);
        if (!matchesCol && !matchesOp && !matchesCat && !matchesRationale) {
          return false;
        }
      }

      return true;
    });
  }, [allRecs, selections, activeFilter, searchQuery]);

  if (!cleaningPlan) {
    return (
      <Card className="p-12 text-center space-y-3">
        <div className="w-12 h-12 rounded-full bg-primary-soft border border-primary/20 flex items-center justify-center mx-auto text-primary">
          <Sparkle className="w-6 h-6 animate-pulse" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-foreground">Generating Cleaning Plan</h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            Evaluating data profile and quality observations to generate deterministic cleaning recommendations...
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Plan Summary Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">
            Total Opportunities
          </span>
          <div className="text-xl font-bold font-mono text-foreground">
            {cleaningPlan.total_recommendations}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Deterministic findings
          </span>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-emerald-600 dark:text-emerald-400 font-mono">
            Safe & Recommended
          </span>
          <div className="text-xl font-bold font-mono text-emerald-500">
            {cleaningPlan.safe_count}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Low risk • Preselected
          </span>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-amber-600 dark:text-amber-400 font-mono">
            Requires Review
          </span>
          <div className={`text-xl font-bold font-mono ${cleaningPlan.review_required_count > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {cleaningPlan.review_required_count}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            User approval needed
          </span>
        </Card>

        <Card className="p-4 space-y-1">
          <span className="text-3xs uppercase tracking-wider text-primary font-mono">
            Selected for Plan
          </span>
          <div className="text-xl font-bold font-mono text-primary">
            {selectedCount} <span className="text-xs font-normal text-muted-foreground">/ {cleaningPlan.total_recommendations}</span>
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Configured actions
          </span>
        </Card>
      </div>

      {/* 2. Filter & Selection Management Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-2 border-b border-border">
        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setActiveFilter('ALL')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'ALL'
                ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            All ({cleaningPlan.total_recommendations})
          </button>

          <button
            onClick={() => setActiveFilter('RECOMMENDED')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'RECOMMENDED'
                ? 'bg-emerald-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Recommended ({cleaningPlan.recommended_count})
          </button>

          <button
            onClick={() => setActiveFilter('REVIEW_REQUIRED')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'REVIEW_REQUIRED'
                ? 'bg-amber-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Review Required ({cleaningPlan.review_required_count})
          </button>

          <button
            onClick={() => setActiveFilter('SELECTED')}
            className={`px-3 py-1 text-xs font-mono rounded-md transition-colors ${
              activeFilter === 'SELECTED'
                ? 'bg-blue-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Selected ({selectedCount})
          </button>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Filter recommendations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="text-xs bg-surface border border-border rounded px-2.5 py-1 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary font-mono w-44"
          />

          <Button
            variant="ghost"
            size="xs"
            onClick={selectAllSafe}
            className="text-3xs font-mono"
          >
            Select All Safe
          </Button>

          <Button
            variant="ghost"
            size="xs"
            onClick={deselectAll}
            className="text-3xs font-mono text-muted-foreground hover:text-foreground"
          >
            Deselect All
          </Button>
        </div>
      </div>

      {/* 3. Recommendation List */}
      <div className="space-y-4">
        {filteredRecommendations.map((rec) => {
          const isSelected = !!selections[rec.recommendation_id];

          const riskBadgeVariant: 'green' | 'amber' | 'red' =
            rec.risk_level === 'LOW'
              ? 'green'
              : rec.risk_level === 'MEDIUM'
              ? 'amber'
              : 'red';

          const confidenceVariant: 'green' | 'amber' | 'slate' =
            rec.confidence_level === 'HIGH'
              ? 'green'
              : rec.confidence_level === 'MEDIUM'
              ? 'amber'
              : 'slate';

          return (
            <Card
              key={rec.recommendation_id}
              className={`p-5 border transition-all ${
                isSelected
                  ? 'border-primary/50 bg-primary-soft/10 shadow-xs'
                  : 'border-border bg-surface opacity-85 hover:opacity-100'
              }`}
            >
              <div className="space-y-3.5">
                {/* Card Top Row: Checkbox, Target, Operation & Badges */}
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => toggleSelection(rec.recommendation_id)}
                      className="mt-0.5 text-primary hover:text-primary-hover focus:outline-none"
                      title={isSelected ? 'Deselect from plan' : 'Select for plan'}
                    >
                      {isSelected ? (
                        <CheckSquare className="w-5 h-5 text-primary" />
                      ) : (
                        <Square className="w-5 h-5 text-muted-foreground hover:text-foreground" />
                      )}
                    </button>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        {rec.column_name ? (
                          <span className="text-xs font-bold font-mono text-foreground px-2 py-0.5 bg-surface-muted border border-border rounded">
                            {rec.column_name}
                          </span>
                        ) : (
                          <Badge variant="blue" size="xs">
                            DATASET-WIDE
                          </Badge>
                        )}

                        <span className="text-xs font-bold font-mono text-foreground">
                          {rec.operation.replace(/_/g, ' ')}
                        </span>

                        <Badge variant="slate" size="xs">
                          {rec.category.replace(/_/g, ' ')}
                        </Badge>
                      </div>

                      <div className="flex items-center gap-2 text-3xs font-mono text-muted-foreground">
                        <span>
                          Affected: <strong className="text-foreground">{rec.affected_rows.toLocaleString()} rows</strong> ({rec.affected_percentage}%)
                        </span>
                        <span>•</span>
                        <span>
                          ID: <span className="font-mono text-foreground">{rec.recommendation_id}</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Badges on Right */}
                  <div className="flex items-center gap-2">
                    <Badge variant={riskBadgeVariant} size="xs">
                      Risk: {rec.risk_level}
                    </Badge>
                    <Badge variant={confidenceVariant} size="xs">
                      Confidence: {Math.round(rec.confidence * 100)}% ({rec.confidence_level})
                    </Badge>
                    {rec.requires_review && (
                      <Badge variant="amber" size="xs">
                        Review Required
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Explanation & Rationale */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-border/60 text-xs">
                  <div className="space-y-1">
                    <span className="text-3xs uppercase tracking-wider font-mono text-muted-foreground block">
                      Rationale (Why recommended)
                    </span>
                    <p className="text-foreground leading-relaxed text-xs">
                      {rec.rationale}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <span className="text-3xs uppercase tracking-wider font-mono text-muted-foreground block">
                      Expected Effect (What will happen)
                    </span>
                    <p className="text-muted-foreground leading-relaxed text-xs">
                      {rec.expected_effect}
                    </p>
                  </div>
                </div>

                {/* Evidence Statements */}
                {rec.evidence && rec.evidence.length > 0 && (
                  <div className="pt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-3xs uppercase font-mono text-muted-foreground mr-1">
                      Evidence:
                    </span>
                    {rec.evidence.map((evStr, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 bg-surface-muted/70 border border-border/80 rounded text-3xs font-mono text-foreground"
                      >
                        {evStr}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          );
        })}

        {filteredRecommendations.length === 0 && (
          <Card className="p-8 text-center space-y-2">
            <div className="w-10 h-10 rounded-full bg-surface-muted flex items-center justify-center mx-auto text-muted-foreground">
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            </div>
            <h4 className="text-sm font-bold text-foreground">No Recommendations Found</h4>
            <p className="text-xs text-muted-foreground font-mono">
              No cleaning recommendations match the current filter or search criteria.
            </p>
          </Card>
        )}
      </div>

      {/* 4. Review Completion Bar (Read-Only Preview Handoff) */}
      <Card className="p-4 border border-primary/20 bg-primary-soft/10 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg text-primary shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-bold text-foreground font-mono">
                Cleaning Plan Status
              </h4>
              <Badge variant="blue" size="xs">
                {selectedCount} of {cleaningPlan.total_recommendations} Selected
              </Badge>
            </div>
            <p className="text-3xs text-muted-foreground mt-0.5">
              Deterministic plan established. Review complete — transformation preview and execution will follow in Part 5.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            disabled
            className="opacity-70 cursor-not-allowed font-mono text-xs"
            rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
          >
            Preview & Apply (Part 5)
          </Button>
        </div>
      </Card>
    </div>
  );
};
