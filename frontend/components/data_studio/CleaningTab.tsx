'use client';

import React, { useState, useMemo } from 'react';
import {
  Sparkles,
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
  Eye,
  Play,
  RotateCcw,
  X,
  Check,
  AlertCircle,
  FileCheck2,
  Table,
  Zap,
  Download,
  Sliders,
  Wand2,
  PlusCircle,
  Trash2,
  Columns,
  Rows,
  Copy,
  Tag,
  SlidersHorizontal,
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import { Button } from '../Button';
import {
  CleaningExecutionResult,
  CleaningPlan,
  CleaningPreviewResult,
  CleaningRecommendation,
  ColumnTransformPreviewResult,
  CustomColumnTransformation,
  DatasetMetadata,
  DropColumnsPreviewResult,
  DuplicateRemovalPreviewResult,
  FilterCondition,
  MultiValueApplyResponse,
  MultiValueCandidate,
  MultiValuePreviewResult,
  OperationExecutionResult,
  QualityAssessment,
  RegisterCleanedDatasetResponse,
  RowFilterPreviewResult,
  SampleCellChange,
  SemanticProfile,
  SemanticRoleOverrideResponse,
  StructuralQualityRecommendation,
} from '../../lib/types';
import {
  applyCleaningPlan,
  applyDropColumns,
  applyFilterRows,
  applyMultiValue,
  applyRemoveDuplicates,
  applySemanticRoleOverride,
  getDatasetDownloadUrl,
  getMultiValueCandidates,
  getStructuralRecommendations,
  previewCleaningPlan,
  previewColumnTransformation,
  previewDropColumns,
  previewFilterRows,
  previewMultiValue,
  previewRemoveDuplicates,
  previewSemanticRoleOverride,
  registerCleanedDataset,
} from '../../lib/api';

interface CleaningTabProps {
  metadata: DatasetMetadata;
  cleaningPlan: CleaningPlan | null;
  semanticProfile: SemanticProfile | null;
  qualityAssessment: QualityAssessment | null;
  isLoadingPlan?: boolean;
  planError?: string | null;
  onRetryPlan?: () => void;
  onSelectDataset?: (datasetId: string) => void;
  onDatasetRegistered?: (newDatasetId: string) => void;
}

type FilterStatus = 'ALL' | 'RECOMMENDED' | 'REVIEW_REQUIRED' | 'SELECTED';
type ExecutionState = 'idle' | 'applying' | 'validating' | 'complete' | 'error';
type RegistrationState = 'idle' | 'registering' | 'registered' | 'error';

export const CleaningTab: React.FC<CleaningTabProps> = ({
  metadata,
  cleaningPlan,
  semanticProfile,
  qualityAssessment,
  isLoadingPlan = false,
  planError = null,
  onRetryPlan,
  onSelectDataset,
  onDatasetRegistered,
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

  // Local state for user-selected method overrides (recommendation_id -> selected_operation)
  const [methodOverrides, setMethodOverrides] = useState<Record<string, string>>({});
  // Local state for user-specified custom values (recommendation_id -> custom_value_string)
  const [customValues, setCustomValues] = useState<Record<string, string>>({});

  const [activeFilter, setActiveFilter] = useState<FilterStatus>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // User-Controlled Column Transformations State
  const availableColumns = useMemo<string[]>(() => {
    if (metadata?.columns && Array.isArray(metadata.columns) && metadata.columns.length > 0) {
      return metadata.columns.map((c) => (typeof c === 'string' ? c : c.original_name));
    }
    return [];
  }, [metadata]);

  const [selectedCol, setSelectedCol] = useState<string>(() => {
    if (metadata?.columns && Array.isArray(metadata.columns) && metadata.columns.length > 0) {
      const first = metadata.columns[0];
      return typeof first === 'string' ? first : first.original_name;
    }
    return '';
  });
  const [selectedTransformType, setSelectedTransformType] = useState<string>('CONVERT_NUMERIC');
  const [customTransformVal, setCustomTransformVal] = useState<string>('');
  const [allowFractional, setAllowFractional] = useState<boolean>(false);
  const [colPreviewLoading, setColPreviewLoading] = useState<boolean>(false);
  const [colPreviewResult, setColPreviewResult] = useState<ColumnTransformPreviewResult | null>(null);
  const [colPreviewError, setColPreviewError] = useState<string | null>(null);
  const [customTransformations, setCustomTransformations] = useState<CustomColumnTransformation[]>([]);

  // Multi-Valued Cells State (Part 6.3)
  const [mvCandidates, setMvCandidates] = useState<MultiValueCandidate[]>([]);
  const [isLoadingMvCandidates, setIsLoadingMvCandidates] = useState<boolean>(false);
  const [mvCandidatesError, setMvCandidatesError] = useState<string | null>(null);

  const [mvSelectedActions, setMvSelectedActions] = useState<Record<string, 'SPLIT_COLUMNS' | 'EXPAND_ROWS' | 'KEEP'>>({});
  const [mvCustomDelimiters, setMvCustomDelimiters] = useState<Record<string, string>>({});

  const [activeMvCol, setActiveMvCol] = useState<string | null>(null);
  const [mvPreviewLoading, setMvPreviewLoading] = useState<boolean>(false);
  const [mvPreviewResult, setMvPreviewResult] = useState<MultiValuePreviewResult | null>(null);
  const [mvPreviewError, setMvPreviewError] = useState<string | null>(null);

  const [mvApplyLoading, setMvApplyLoading] = useState<boolean>(false);
  const [mvApplySuccess, setMvApplySuccess] = useState<string | null>(null);
  const [mvApplyError, setMvApplyError] = useState<string | null>(null);

  // ----------------------------------------------------
  // PART 6.4 — STRUCTURAL CLEANING & SEMANTIC ROLES STATE
  // ----------------------------------------------------

  // Active Structural Cleaning Subtab
  const [activeStructTab, setActiveStructTab] = useState<'DROP_COLUMNS' | 'FILTER_ROWS' | 'DUPLICATES' | 'RECOMMENDATIONS' | 'SEMANTIC_ROLES'>('RECOMMENDATIONS');

  // Structural Quality Recommendations
  const [structRecs, setStructRecs] = useState<StructuralQualityRecommendation[]>([]);
  const [isLoadingStructRecs, setIsLoadingStructRecs] = useState<boolean>(false);
  const [structRecsError, setStructRecsError] = useState<string | null>(null);

  // Column Dropping State
  const [selectedDropCols, setSelectedDropCols] = useState<string[]>([]);
  const [dropPreviewLoading, setDropPreviewLoading] = useState<boolean>(false);
  const [dropPreviewResult, setDropPreviewResult] = useState<DropColumnsPreviewResult | null>(null);
  const [dropPreviewError, setDropPreviewError] = useState<string | null>(null);
  const [dropApplyLoading, setDropApplyLoading] = useState<boolean>(false);
  const [dropApplySuccess, setDropApplySuccess] = useState<string | null>(null);
  const [dropApplyError, setDropApplyError] = useState<string | null>(null);

  // Row Filtering State
  const [filterConditions, setFilterConditions] = useState<FilterCondition[]>([
    { column: '', operator: 'equals', value: '' },
  ]);
  const [filterLogicalOp, setFilterLogicalOp] = useState<'AND' | 'OR'>('AND');
  const [filterPreviewLoading, setFilterPreviewLoading] = useState<boolean>(false);
  const [filterPreviewResult, setFilterPreviewResult] = useState<RowFilterPreviewResult | null>(null);
  const [filterPreviewError, setFilterPreviewError] = useState<string | null>(null);
  const [filterApplyLoading, setFilterApplyLoading] = useState<boolean>(false);
  const [filterApplySuccess, setFilterApplySuccess] = useState<string | null>(null);
  const [filterApplyError, setFilterApplyError] = useState<string | null>(null);

  // Duplicate Rows State
  const [dupKeepStrategy, setDupKeepStrategy] = useState<'first' | 'last'>('first');
  const [dupPreviewLoading, setDupPreviewLoading] = useState<boolean>(false);
  const [dupPreviewResult, setDupPreviewResult] = useState<DuplicateRemovalPreviewResult | null>(null);
  const [dupPreviewError, setDupPreviewError] = useState<string | null>(null);
  const [dupApplyLoading, setDupApplyLoading] = useState<boolean>(false);
  const [dupApplySuccess, setDupApplySuccess] = useState<string | null>(null);
  const [dupApplyError, setDupApplyError] = useState<string | null>(null);

  // Semantic Role Overrides State
  const [selectedRoleCol, setSelectedRoleCol] = useState<string>('');
  const [selectedRoleValue, setSelectedRoleValue] = useState<string>('IDENTIFIER');
  const [rolePreviewLoading, setRolePreviewLoading] = useState<boolean>(false);
  const [rolePreviewResult, setRolePreviewResult] = useState<SemanticRoleOverrideResponse | null>(null);
  const [rolePreviewError, setRolePreviewError] = useState<string | null>(null);
  const [roleApplyLoading, setRoleApplyLoading] = useState<boolean>(false);
  const [roleApplySuccess, setRoleApplySuccess] = useState<string | null>(null);
  const [roleApplyError, setRoleApplyError] = useState<string | null>(null);
  const [userRoleOverrides, setUserRoleOverrides] = useState<Record<string, string>>({});

  // Preview & Execution State
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewResult, setPreviewResult] = useState<CleaningPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [executionState, setExecutionState] = useState<ExecutionState>('idle');
  const [executionResult, setExecutionResult] = useState<CleaningExecutionResult | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);

  // Registration & Download State
  const [registrationState, setRegistrationState] = useState<RegistrationState>('idle');
  const [registeredData, setRegisteredData] = useState<RegisterCleanedDatasetResponse | null>(null);
  const [registrationError, setRegistrationError] = useState<string | null>(null);

  // Update selections when cleaningPlan changes (e.g. switching datasets)
  React.useEffect(() => {
    if (!cleaningPlan) {
      setSelections({});
      setMethodOverrides({});
      setCustomValues({});
      setCustomTransformations([]);
      setColPreviewResult(null);
      setColPreviewError(null);
      setPreviewResult(null);
      setExecutionResult(null);
      setExecutionState('idle');
      setRegistrationState('idle');
      setRegisteredData(null);
      setRegistrationError(null);
      return;
    }
    const initial: Record<string, boolean> = {};
    for (const rec of cleaningPlan.recommendations) {
      initial[rec.recommendation_id] = rec.default_selected;
    }
    setSelections(initial);
    setMethodOverrides({});
    setCustomValues({});
    setCustomTransformations([]);
    setColPreviewResult(null);
    setColPreviewError(null);
    setPreviewResult(null);
    setExecutionResult(null);
    setExecutionState('idle');
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);
  }, [cleaningPlan?.dataset_id]);

  React.useEffect(() => {
    if (availableColumns.length > 0 && (!selectedCol || !availableColumns.includes(selectedCol))) {
      setSelectedCol(availableColumns[0]);
    }
  }, [availableColumns, selectedCol]);

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

  const selectedIds = useMemo(() => {
    return allRecs
      .filter((r) => selections[r.recommendation_id])
      .map((r) => r.recommendation_id);
  }, [allRecs, selections]);

  const selectedCount = selectedIds.length;

  const modifiedCount = useMemo(() => {
    return allRecs.filter(
      (r) =>
        (methodOverrides[r.recommendation_id] && methodOverrides[r.recommendation_id] !== r.operation) ||
        (customValues[r.recommendation_id] && customValues[r.recommendation_id].trim() !== '')
    ).length;
  }, [allRecs, methodOverrides, customValues]);

  const isDiagnosticOnly = (op: string) => {
    return (
      op.startsWith('REVIEW_') ||
      op === 'REVIEW_OUTLIERS' ||
      op === 'REVIEW_CONSTANT_COLUMN' ||
      op === 'REVIEW_DATETIME_MISSING' ||
      op === 'REVIEW_IDENTIFIER_MISSING' ||
      op === 'REVIEW_HIGH_MISSINGNESS'
    );
  };

  const selectedColInfo = useMemo(() => {
    if (!selectedCol) return null;
    const colMeta = metadata?.columns?.find(
      (c) => (typeof c === 'string' ? c : c.original_name) === selectedCol
    );
    const semCol = semanticProfile?.column_evidences?.[selectedCol];
    const dtype = (typeof colMeta === 'object' ? colMeta?.detected_datatype : null) || 'Unknown';
    const role = semCol?.candidate_role || (typeof colMeta === 'object' ? colMeta?.semantic_role : null) || 'UNKNOWN';
    const nullCount = (typeof colMeta === 'object' ? colMeta?.null_count : null) ?? 0;
    const nullPct =
      (typeof colMeta === 'object' ? colMeta?.null_percentage : null) ??
      (metadata?.row_count && metadata.row_count > 0 ? (nullCount / metadata.row_count) * 100 : 0);
    return {
      dtype,
      role,
      nullCount,
      nullPct: Math.round(nullPct * 10) / 10,
    };
  }, [selectedCol, semanticProfile, metadata]);

  const getTransformExplanation = () => {
    if (!selectedColInfo) return '';
    const { nullCount } = selectedColInfo;

    switch (selectedTransformType) {
      case 'CONVERT_NUMERIC':
      case 'CONVERT_FLOAT':
        return `${nullCount > 0 ? `${nullCount} values are missing and the ` : 'The '}column contains numeric-looking values. Converting to numeric parses numbers and converts unparseable tokens to missing (null). Semantic role refreshes to MEASURE.`;
      case 'CONVERT_INTEGER':
        return `Converts values to whole integers. If fractional values exist, conversion safely halts to prevent data loss unless explicitly confirmed.`;
      case 'CONVERT_DATETIME':
        return `Parses date and timestamp strings using standard patterns. Unparseable formats become missing.`;
      case 'NORMALIZE_BOOLEAN':
      case 'CONVERT_BOOLEAN':
        return `Standardizes boolean representations (true/false, yes/no, 1/0) into strict boolean booleans.`;
      case 'CONVERT_STRING':
        return `Casts column values to clean text/string representation.`;
      case 'TRIM_WHITESPACE':
        return `Strips leading and trailing spaces, tabs, and newline characters from string values.`;
      case 'NORMALIZE_EMPTY_STRINGS':
        return `Converts empty ("") and whitespace-only text cells into true null/missing values.`;
      case 'IMPUTE_MEDIAN':
        return `Fills ${nullCount} missing values with the median of valid numeric values.`;
      case 'IMPUTE_MEAN':
        return `Fills ${nullCount} missing values with the arithmetic mean of valid numeric values.`;
      case 'IMPUTE_MODE':
        return `Fills ${nullCount} missing values with the most frequent value.`;
      case 'IMPUTE_UNKNOWN':
        return `Fills ${nullCount} missing values with the standard placeholder "Unknown".`;
      case 'IMPUTE_SPECIFIC_VALUE':
        return `Fills ${nullCount} missing values with user-provided constant "${customTransformVal || '...'}" after type validation.`;
      case 'LEAVE_UNCHANGED':
        return `Preserves missing values without modification.`;
      default:
        return 'Apply deterministic transformation to column.';
    }
  };

  // Preview Action for Single User Column Transformation
  const handlePreviewColumnTransform = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || !selectedCol) return;
    setColPreviewLoading(true);
    setColPreviewError(null);
    try {
      const res = await previewColumnTransformation(targetDatasetId, {
        column_name: selectedCol,
        operation: selectedTransformType,
        custom_value: customTransformVal,
        allow_fractional_truncation: allowFractional,
      });
      setColPreviewResult(res);
      if (!res.is_valid && res.error_message) {
        setColPreviewError(res.error_message);
      }
    } catch (err: any) {
      setColPreviewError(err.message || 'Failed to preview column transformation.');
      setColPreviewResult(null);
    } finally {
      setColPreviewLoading(false);
    }
  };

  // Direct Apply for Single User Column Transformation
  const handleApplySingleTransform = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || !selectedCol) return;
    setIsPreviewOpen(false);
    setExecutionState('applying');
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);

    const singleTransform: CustomColumnTransformation = {
      column_name: selectedCol,
      operation: selectedTransformType,
      custom_value: customTransformVal,
      allow_fractional_truncation: allowFractional,
      source: 'USER',
    };

    try {
      const timer = setTimeout(() => {
        setExecutionState('validating');
      }, 400);

      const res = await applyCleaningPlan(
        targetDatasetId,
        [],
        {},
        {},
        [singleTransform]
      );
      clearTimeout(timer);
      setExecutionResult(res);
      setExecutionState('complete');
    } catch (err: any) {
      setExecutionError(err.message || 'Failed to execute column transformation.');
      setExecutionState('error');
    }
  };

  const handleQueueCustomTransform = () => {
    if (!selectedCol) return;
    const newTransform: CustomColumnTransformation = {
      column_name: selectedCol,
      operation: selectedTransformType,
      custom_value: customTransformVal,
      allow_fractional_truncation: allowFractional,
      source: 'USER',
    };
    setCustomTransformations((prev) => {
      const filtered = prev.filter((t) => t.column_name !== selectedCol);
      return [...filtered, newTransform];
    });
  };

  const handleRemoveCustomTransform = (colName: string) => {
    setCustomTransformations((prev) => prev.filter((t) => t.column_name !== colName));
  };

  const fetchMvCandidates = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId) return;
    setIsLoadingMvCandidates(true);
    setMvCandidatesError(null);
    try {
      const res = await getMultiValueCandidates(datasetId);
      setMvCandidates(res.candidates || []);
      const initialActions: Record<string, 'SPLIT_COLUMNS' | 'EXPAND_ROWS' | 'KEEP'> = {};
      const initialDelims: Record<string, string> = {};
      for (const cand of res.candidates || []) {
        initialActions[cand.column_name] =
          cand.recommendation === 'EXPAND_ROWS'
            ? 'EXPAND_ROWS'
            : cand.recommendation === 'SPLIT_COLUMNS'
            ? 'SPLIT_COLUMNS'
            : 'KEEP';
        initialDelims[cand.column_name] = cand.detected_delimiter || ',';
      }
      setMvSelectedActions((prev) => ({ ...initialActions, ...prev }));
      setMvCustomDelimiters((prev) => ({ ...initialDelims, ...prev }));
    } catch (err: any) {
      setMvCandidatesError(err.message || 'Failed to detect multi-valued cell candidates.');
    } finally {
      setIsLoadingMvCandidates(false);
    }
  };

  React.useEffect(() => {
    fetchMvCandidates();
    setMvPreviewResult(null);
    setMvPreviewError(null);
    setActiveMvCol(null);
    setMvApplySuccess(null);
    setMvApplyError(null);
  }, [metadata?.dataset_id]);

  const handlePreviewMultiValue = async (colName: string) => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId) return;
    setActiveMvCol(colName);
    setMvPreviewLoading(true);
    setMvPreviewError(null);
    setMvPreviewResult(null);
    setMvApplySuccess(null);
    setMvApplyError(null);

    const action = mvSelectedActions[colName] || 'SPLIT_COLUMNS';
    const delimiter = mvCustomDelimiters[colName] || ',';

    try {
      const res = await previewMultiValue(datasetId, {
        column_name: colName,
        action,
        delimiter,
      });
      setMvPreviewResult(res);
    } catch (err: any) {
      setMvPreviewError(err.message || 'Failed to generate multi-value preview.');
    } finally {
      setMvPreviewLoading(false);
    }
  };

  const handleApplyMultiValue = async (colName: string) => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId) return;
    setMvApplyLoading(true);
    setMvApplyError(null);
    setMvApplySuccess(null);

    const action = mvSelectedActions[colName] || 'SPLIT_COLUMNS';
    const delimiter = mvCustomDelimiters[colName] || ',';

    try {
      const res = await applyMultiValue(datasetId, {
        column_name: colName,
        action,
        delimiter,
      });
      const actionLabel =
        action === 'SPLIT_COLUMNS'
          ? 'Split Columns'
          : action === 'EXPAND_ROWS'
          ? 'Expand Rows'
          : 'Keep As Is';
      setMvApplySuccess(
        `Successfully applied ${actionLabel} on "${colName}". Cleaned dataset updated (${res.cleaned_row_count} rows, ${res.cleaned_column_count} columns).`
      );
      setMvPreviewResult(null);
      await fetchMvCandidates();
      if (onRetryPlan) {
        onRetryPlan();
      }
    } catch (err: any) {
      setMvApplyError(err.message || 'Failed to apply multi-value transformation.');
    } finally {
      setMvApplyLoading(false);
    }
  };

  // ----------------------------------------------------
  // PART 6.4 — STRUCTURAL CLEANING HANDLERS
  // ----------------------------------------------------

  const fetchStructRecs = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId) return;
    setIsLoadingStructRecs(true);
    setStructRecsError(null);
    try {
      const res = await getStructuralRecommendations(datasetId);
      setStructRecs(res.recommendations || []);
    } catch (err: any) {
      setStructRecsError(err.message || 'Failed to fetch structural recommendations.');
    } finally {
      setIsLoadingStructRecs(false);
    }
  };

  React.useEffect(() => {
    fetchStructRecs();
    setDropPreviewResult(null);
    setDropPreviewError(null);
    setDropApplySuccess(null);
    setDropApplyError(null);
    setFilterPreviewResult(null);
    setFilterPreviewError(null);
    setFilterApplySuccess(null);
    setFilterApplyError(null);
    setDupPreviewResult(null);
    setDupPreviewError(null);
    setDupApplySuccess(null);
    setDupApplyError(null);
    setRolePreviewResult(null);
    setRolePreviewError(null);
    setRoleApplySuccess(null);
    setRoleApplyError(null);

    if (availableColumns.length > 0) {
      setSelectedRoleCol((prev) => (prev && availableColumns.includes(prev) ? prev : availableColumns[0]));
      setFilterConditions((prev) => {
        if (prev.length === 0 || !prev[0].column || !availableColumns.includes(prev[0].column)) {
          return [{ column: availableColumns[0], operator: 'equals', value: '' }];
        }
        return prev;
      });
    }
  }, [metadata?.dataset_id, availableColumns]);

  // Handlers for Column Dropping
  const handleToggleDropCol = (colName: string) => {
    setSelectedDropCols((prev) =>
      prev.includes(colName) ? prev.filter((c) => c !== colName) : [...prev, colName]
    );
    setDropPreviewResult(null);
  };

  const handlePreviewDropColumns = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId || selectedDropCols.length === 0) return;
    setDropPreviewLoading(true);
    setDropPreviewError(null);
    setDropPreviewResult(null);
    setDropApplySuccess(null);
    setDropApplyError(null);
    try {
      const res = await previewDropColumns(datasetId, { columns: selectedDropCols });
      setDropPreviewResult(res);
    } catch (err: any) {
      setDropPreviewError(err.message || 'Failed to preview column drop.');
    } finally {
      setDropPreviewLoading(false);
    }
  };

  const handleApplyDropColumns = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId || selectedDropCols.length === 0) return;
    setDropApplyLoading(true);
    setDropApplyError(null);
    setDropApplySuccess(null);
    try {
      const res = await applyDropColumns(datasetId, { columns: selectedDropCols });
      setDropApplySuccess(
        `Successfully dropped ${selectedDropCols.length} column(s). Cleaned dataset now has ${res.cleaned_column_count} columns and ${res.cleaned_row_count} rows.`
      );
      setSelectedDropCols([]);
      setDropPreviewResult(null);
      await fetchStructRecs();
      if (onRetryPlan) onRetryPlan();
    } catch (err: any) {
      setDropApplyError(err.message || 'Failed to apply column drop.');
    } finally {
      setDropApplyLoading(false);
    }
  };

  // Handlers for Row Filtering
  const handleAddCondition = () => {
    setFilterConditions((prev) => [
      ...prev,
      { column: availableColumns[0] || '', operator: 'equals', value: '' },
    ]);
    setFilterPreviewResult(null);
  };

  const handleRemoveCondition = (index: number) => {
    setFilterConditions((prev) => prev.filter((_, i) => i !== index));
    setFilterPreviewResult(null);
  };

  const handleUpdateCondition = (index: number, field: keyof FilterCondition, value: any) => {
    setFilterConditions((prev) =>
      prev.map((c, i) => (i === index ? { ...c, [field]: value } : c))
    );
    setFilterPreviewResult(null);
  };

  const handlePreviewFilterRows = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId || filterConditions.length === 0) return;
    setFilterPreviewLoading(true);
    setFilterPreviewError(null);
    setFilterPreviewResult(null);
    setFilterApplySuccess(null);
    setFilterApplyError(null);
    try {
      const res = await previewFilterRows(datasetId, {
        conditions: filterConditions,
        logical_operator: filterLogicalOp,
      });
      setFilterPreviewResult(res);
    } catch (err: any) {
      setFilterPreviewError(err.message || 'Failed to preview row filtering.');
    } finally {
      setFilterPreviewLoading(false);
    }
  };

  const handleApplyFilterRows = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId || filterConditions.length === 0) return;
    setFilterApplyLoading(true);
    setFilterApplyError(null);
    setFilterApplySuccess(null);
    try {
      const res = await applyFilterRows(datasetId, {
        conditions: filterConditions,
        logical_operator: filterLogicalOp,
      });
      setFilterApplySuccess(
        `Successfully applied row filtering. Cleaned dataset now has ${res.cleaned_row_count} rows (${res.cleaned_column_count} columns).`
      );
      setFilterPreviewResult(null);
      await fetchStructRecs();
      if (onRetryPlan) onRetryPlan();
    } catch (err: any) {
      setFilterApplyError(err.message || 'Failed to apply row filter.');
    } finally {
      setFilterApplyLoading(false);
    }
  };

  // Handlers for Duplicate Removal
  const handlePreviewRemoveDuplicates = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId) return;
    setDupPreviewLoading(true);
    setDupPreviewError(null);
    setDupPreviewResult(null);
    setDupApplySuccess(null);
    setDupApplyError(null);
    try {
      const res = await previewRemoveDuplicates(datasetId, { keep_strategy: dupKeepStrategy });
      setDupPreviewResult(res);
    } catch (err: any) {
      setDupPreviewError(err.message || 'Failed to preview duplicate removal.');
    } finally {
      setDupPreviewLoading(false);
    }
  };

  const handleApplyRemoveDuplicates = async () => {
    const datasetId = metadata?.dataset_id;
    if (!datasetId) return;
    setDupApplyLoading(true);
    setDupApplyError(null);
    setDupApplySuccess(null);
    try {
      const res = await applyRemoveDuplicates(datasetId, { keep_strategy: dupKeepStrategy });
      setDupApplySuccess(
        `Successfully removed duplicate rows. Cleaned dataset now has ${res.cleaned_row_count} rows.`
      );
      setDupPreviewResult(null);
      await fetchStructRecs();
      if (onRetryPlan) onRetryPlan();
    } catch (err: any) {
      setDupApplyError(err.message || 'Failed to apply duplicate removal.');
    } finally {
      setDupApplyLoading(false);
    }
  };

  // Handlers for Semantic Role Overrides
  const handlePreviewSemanticRoleOverride = async (colName?: string, roleVal?: string) => {
    const datasetId = metadata?.dataset_id;
    const targetCol = colName || selectedRoleCol;
    const targetRole = roleVal || selectedRoleValue;
    if (!datasetId || !targetCol) return;
    setRolePreviewLoading(true);
    setRolePreviewError(null);
    setRolePreviewResult(null);
    setRoleApplySuccess(null);
    setRoleApplyError(null);
    try {
      const res = await previewSemanticRoleOverride(datasetId, {
        column_name: targetCol,
        selected_role: targetRole,
      });
      setRolePreviewResult(res);
    } catch (err: any) {
      setRolePreviewError(err.message || 'Failed to preview semantic role override.');
    } finally {
      setRolePreviewLoading(false);
    }
  };

  const handleApplySemanticRoleOverride = async (colName?: string, roleVal?: string) => {
    const datasetId = metadata?.dataset_id;
    const targetCol = colName || selectedRoleCol;
    const targetRole = roleVal || selectedRoleValue;
    if (!datasetId || !targetCol) return;
    setRoleApplyLoading(true);
    setRoleApplyError(null);
    setRoleApplySuccess(null);
    try {
      const res = await applySemanticRoleOverride(datasetId, {
        column_name: targetCol,
        selected_role: targetRole,
      });
      setUserRoleOverrides((prev) => ({ ...prev, [targetCol]: res.selected_role }));
      setRoleApplySuccess(
        `Successfully designated "${targetCol}" as authoritative semantic role "${res.selected_role}". Physical type (${res.physical_dtype}) is preserved.`
      );
      setRolePreviewResult(null);
      await fetchStructRecs();
      if (onRetryPlan) onRetryPlan();
    } catch (err: any) {
      setRoleApplyError(err.message || 'Failed to apply semantic role override.');
    } finally {
      setRoleApplyLoading(false);
    }
  };

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

  // Preview Action for Batch Plan
  const handleGeneratePreview = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || (selectedIds.length === 0 && customTransformations.length === 0)) return;
    setIsLoadingPreview(true);
    setPreviewError(null);
    try {
      const res = await previewCleaningPlan(
        targetDatasetId,
        selectedIds,
        methodOverrides,
        customValues,
        customTransformations
      );
      setPreviewResult(res);
      setIsPreviewOpen(true);
    } catch (err: any) {
      setPreviewError(err.message || 'Failed to generate cleaning preview.');
      setIsPreviewOpen(true);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  // Apply Action for Batch Plan
  const handleApplyCleaning = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId || (selectedIds.length === 0 && customTransformations.length === 0)) return;
    setIsPreviewOpen(false);
    setExecutionState('applying');
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);

    try {
      const timer = setTimeout(() => {
        setExecutionState('validating');
      }, 400);

      const res = await applyCleaningPlan(
        targetDatasetId,
        selectedIds,
        methodOverrides,
        customValues,
        customTransformations
      );
      clearTimeout(timer);
      setExecutionResult(res);
      setExecutionState('complete');
    } catch (err: any) {
      setExecutionError(err.message || 'Failed to execute cleaning plan.');
      setExecutionState('error');
    }
  };

  // Register Cleaned Dataset Action
  const handleRegisterCleaned = async () => {
    const targetDatasetId = cleaningPlan?.dataset_id || metadata?.dataset_id;
    if (!targetDatasetId) {
      setRegistrationError('No active dataset found for registration.');
      setRegistrationState('error');
      return;
    }
    setRegistrationState('registering');
    setRegistrationError(null);
    try {
      const res = await registerCleanedDataset(targetDatasetId);
      setRegisteredData(res);
      setRegistrationState('registered');
      if (onDatasetRegistered) {
        onDatasetRegistered(res.dataset_id);
      }
    } catch (err: any) {
      let msg = err.message || 'Failed to register cleaned dataset.';
      if (msg.includes('Not Found') || msg.includes('404')) {
        msg = `${msg} (Ensure the backend server has reloaded latest API routes).`;
      }
      setRegistrationError(msg);
      setRegistrationState('error');
    }
  };

  const handleResetExecution = () => {
    setExecutionState('idle');
    setExecutionResult(null);
    setExecutionError(null);
    setRegistrationState('idle');
    setRegisteredData(null);
    setRegistrationError(null);
  };

  // 1. Loading State
  if (isLoadingPlan) {
    return (
      <Card className="p-12 text-center space-y-3">
        <div className="w-10 h-10 mx-auto text-primary">
          <svg className="animate-spin w-10 h-10" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
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

  // 2. Error or Missing Plan State
  if (planError || !cleaningPlan) {
    return (
      <Card className="p-10 text-center space-y-4 border-rose-500/20 bg-rose-500/5 max-w-lg mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-500 flex items-center justify-center mx-auto">
          <AlertTriangle className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-foreground">Unable to Generate Cleaning Plan</h3>
          <p className="text-xs text-muted-foreground">
            {planError || 'No cleaning plan could be generated for this dataset.'}
          </p>
        </div>
        {onRetryPlan && (
          <div className="pt-2">
            <Button variant="primary" size="sm" onClick={onRetryPlan} leftIcon={<Sparkles className="w-3.5 h-3.5" />}>
              Retry Generating Plan
            </Button>
          </div>
        )}
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Execution Running Banner */}
      {(executionState === 'applying' || executionState === 'validating') && (
        <Card className="p-6 border-primary/40 bg-primary-soft/20 text-center space-y-3 animate-pulse">
          <div className="w-8 h-8 mx-auto text-primary">
            <svg className="animate-spin w-8 h-8" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
          <div className="space-y-1">
            <h4 className="text-sm font-bold text-foreground">
              {executionState === 'applying'
                ? 'Applying Selected Cleaning Operations...'
                : 'Validating Invariants & Generating Cleaned In-Memory Dataset...'}
            </h4>
            <p className="text-xs text-muted-foreground">
              Operating safely on a deep copy. Raw source dataset remains 100% immutable.
            </p>
          </div>
        </Card>
      )}

      {/* Execution Error Banner */}
      {executionState === 'error' && (
        <Card className="p-5 border-rose-500/30 bg-rose-500/10 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="text-xs font-bold text-rose-600 dark:text-rose-400">
                Cleaning Execution Failed
              </h4>
              <p className="text-xs text-muted-foreground">
                {executionError || 'An unexpected error occurred during cleaning execution.'}
              </p>
            </div>
          </div>
          <Button variant="secondary" size="xs" onClick={handleResetExecution}>
            Dismiss
          </Button>
        </Card>
      )}

      {/* Cleaned Result Panel (Post Execution) */}
      {executionState === 'complete' && executionResult && (
        <Card className="p-6 border-emerald-500/40 bg-emerald-500/5 space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/20 text-emerald-500 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-foreground">
                    Cleaning Execution Complete
                  </h3>
                  <Badge variant="green" size="xs">
                    Validation: {executionResult.validation?.overall_status || 'PASSED'}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Cleaned in-memory DataFrame generated successfully. Raw source dataset remains untouched.
                </p>
              </div>
            </div>

            <Button
              variant="secondary"
              size="xs"
              onClick={handleResetExecution}
              leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
            >
              Reconfigure Plan
            </Button>
          </div>

          {/* Metrics Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Row Count
              </span>
              <div className="text-lg font-bold text-foreground">
                {executionResult.cleaned_row_count.toLocaleString()}
                <span className="text-2xs font-normal text-muted-foreground ml-1.5">
                  ({executionResult.row_count_change <= 0 ? executionResult.row_count_change : `+${executionResult.row_count_change}`} rows)
                </span>
              </div>
            </div>

            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Operations Applied
              </span>
              <div className="text-lg font-bold text-emerald-500">
                {executionResult.operations_applied}
                <span className="text-2xs font-normal text-muted-foreground ml-1.5">
                  / {executionResult.operations_requested} requested
                </span>
              </div>
            </div>

            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Cells Modified
              </span>
              <div className="text-lg font-bold text-primary">
                {executionResult.total_cells_affected.toLocaleString()}
              </div>
            </div>

            <div className="p-3.5 bg-surface border border-border rounded-lg space-y-1">
              <span className="text-2xs font-medium text-muted-foreground block">
                Checks Passed
              </span>
              <div className="text-lg font-bold text-foreground">
                {executionResult.validation?.passed_checks || 0}
                <span className="text-2xs font-normal text-muted-foreground ml-1.5">
                  / {executionResult.validation?.total_checks || 0} invariant checks
                </span>
              </div>
            </div>
          </div>

          {/* Validation Checks Accordion/List */}
          {executionResult.validation && executionResult.validation.checks.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-border">
              <span className="text-xs font-semibold text-foreground block">
                Post-Cleaning Invariant Verifications
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {executionResult.validation.checks.map((chk, i) => (
                  <div
                    key={i}
                    className="p-3 bg-surface border border-border/80 rounded-md flex items-start gap-2.5 text-xs"
                  >
                    {chk.status === 'PASSED' ? (
                      <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    ) : chk.status === 'WARNING' ? (
                      <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                    ) : (
                      <X className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                    )}
                    <div className="space-y-0.5">
                      <span className="font-semibold text-foreground block text-xs">
                        {chk.check_name}
                      </span>
                      <p className="text-muted-foreground text-2xs leading-relaxed">
                        {chk.message}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Registration and Download Section */}
          <div className="pt-4 border-t border-border space-y-4">
            {registrationState === 'idle' && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 bg-surface rounded-lg border border-border">
                <div className="space-y-1">
                  <h4 className="text-sm font-semibold text-foreground">
                    Register Cleaned Dataset
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    Register this validated in-memory DataFrame as a distinct first-class dataset in Data Studio.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRegisterCleaned}
                  leftIcon={<Sparkles className="w-3.5 h-3.5" />}
                  className="text-xs shrink-0"
                >
                  Register Cleaned Dataset
                </Button>
              </div>
            )}

            {registrationState === 'registering' && (
              <div className="p-4 bg-surface rounded-lg border border-primary/30 flex items-center gap-3 animate-pulse">
                <div className="w-5 h-5 text-primary">
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                </div>
                <div className="space-y-0.5">
                  <span className="text-xs font-bold text-foreground">Registering Cleaned Dataset...</span>
                  <p className="text-2xs text-muted-foreground">
                    Generating schema, statistical profile, semantic intelligence, and readiness assessment.
                  </p>
                </div>
              </div>
            )}

            {registrationState === 'error' && (
              <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg flex items-start justify-between gap-3 text-xs">
                <div className="space-y-1">
                  <span className="font-bold text-rose-600 dark:text-rose-400">Registration Failed</span>
                  <p className="text-muted-foreground text-2xs">{registrationError}</p>
                </div>
                <Button variant="secondary" size="xs" onClick={handleRegisterCleaned}>
                  Retry Registration
                </Button>
              </div>
            )}

            {registrationState === 'registered' && registeredData && (
              <div className="p-4 bg-surface rounded-lg border border-emerald-500/30 space-y-3.5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
                      <Check className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-foreground">Cleaned Dataset Registered</span>
                        <Badge variant="green" size="xs">Ready in Selector</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Available as an independent dataset with complete profiling and semantic intelligence.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    {onSelectDataset && (
                      <Button
                        variant="primary"
                        size="xs"
                        onClick={() => onSelectDataset(registeredData.dataset_id)}
                        leftIcon={<ArrowRight className="w-3.5 h-3.5" />}
                        className="text-xs"
                      >
                        Use Cleaned Dataset
                      </Button>
                    )}

                    <a
                      href={getDatasetDownloadUrl(registeredData.dataset_id, 'csv')}
                      download={`${registeredData.filename}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-border bg-surface hover:bg-surface-muted text-foreground transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-primary" />
                      <span>Download CSV</span>
                    </a>

                    <a
                      href={getDatasetDownloadUrl(registeredData.dataset_id, 'xlsx')}
                      download={`${registeredData.filename.replace(/\.csv$/, '')}.xlsx`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-border bg-surface hover:bg-surface-muted text-foreground transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Download XLSX</span>
                    </a>
                  </div>
                </div>

                {/* Dataset Details Badge Summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2.5 border-t border-border/60 text-xs">
                  <div>
                    <span className="text-2xs text-muted-foreground block">Cleaned Dataset Name</span>
                    <span className="text-foreground font-semibold truncate block mt-0.5">{registeredData.filename}</span>
                  </div>
                  <div>
                    <span className="text-2xs text-muted-foreground block">New Dataset ID</span>
                    <span className="text-foreground font-mono font-medium truncate block mt-0.5">{registeredData.dataset_id}</span>
                  </div>
                  <div>
                    <span className="text-2xs text-muted-foreground block">Dimensions</span>
                    <span className="text-foreground font-semibold block mt-0.5">{registeredData.row_count.toLocaleString()} rows × {registeredData.column_count} cols</span>
                  </div>
                  <div>
                    <span className="text-2xs text-muted-foreground block">Source Dataset</span>
                    <span className="text-foreground font-mono font-medium truncate block mt-0.5">{registeredData.source_dataset_id}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 1. Plan Summary Banner */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-foreground">Cleaning Plan</h2>
            <p className="text-xs text-muted-foreground">
              {cleaningPlan.total_recommendations} cleaning opportunities detected from profiling and quality checks.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card className="p-4 space-y-1">
            <span className="text-xs text-muted-foreground font-medium">
              Issues found
            </span>
            <div className="text-xl font-bold text-foreground">
              {cleaningPlan.total_recommendations}
            </div>
            <span className="text-2xs text-muted-foreground">
              Deterministic opportunities
            </span>
          </Card>

          <Card className="p-4 space-y-1">
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              Recommended
            </span>
            <div className="text-xl font-bold text-emerald-500">
              {cleaningPlan.safe_count}
            </div>
            <span className="text-2xs text-muted-foreground">
              Low risk · Preselected
            </span>
          </Card>

          <Card className="p-4 space-y-1">
            <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
              Requires decision
            </span>
            <div className={`text-xl font-bold ${cleaningPlan.review_required_count > 0 ? 'text-amber-500' : 'text-foreground'}`}>
              {cleaningPlan.review_required_count}
            </div>
            <span className="text-2xs text-muted-foreground">
              User approval needed
            </span>
          </Card>

          <Card className="p-4 space-y-1">
            <span className="text-xs text-primary font-medium">
              Selected
            </span>
            <div className="text-xl font-bold text-primary">
              {selectedCount} <span className="text-xs font-normal text-muted-foreground">/ {cleaningPlan.total_recommendations}</span>
            </div>
            <span className="text-2xs text-muted-foreground">
              Configured batch actions
            </span>
          </Card>
        </div>
      </div>

      {/* 2. User-Controlled Column Transformations Card */}
      <Card className="p-5 border border-border/80 bg-surface shadow-xs space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">
                  Column Transformations
                </h3>
                <Badge variant="blue" size="xs">
                  User Controlled
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Directly configure datatype conversion, string normalization, or missing-value strategies for any column.
              </p>
            </div>
          </div>

          {customTransformations.length > 0 && (
            <Badge variant="blue" size="xs">
              {customTransformations.length} manual operation{customTransformations.length > 1 ? 's' : ''} queued
            </Badge>
          )}
        </div>

        {/* Column Selection & Action Form */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start">
          {/* Column Selector & Details */}
          <div className="md:col-span-4 space-y-2">
            <label className="text-xs font-semibold text-foreground flex items-center justify-between">
              <span>Select Column</span>
              {selectedColInfo && (
                <span className="text-2xs font-normal text-muted-foreground">
                  {selectedColInfo.nullCount > 0 ? `${selectedColInfo.nullCount} missing (${selectedColInfo.nullPct}%)` : 'No missing values'}
                </span>
              )}
            </label>
            <select
              value={selectedCol}
              onChange={(e) => {
                setSelectedCol(e.target.value);
                setColPreviewResult(null);
                setColPreviewError(null);
              }}
              className="w-full text-xs bg-surface-muted/40 border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:border-primary font-medium"
            >
              {availableColumns.map((col) => (
                <option key={col} value={col}>
                  {col}
                </option>
              ))}
            </select>

            {/* Column Metadata Badges */}
            {selectedColInfo && (
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <Badge variant="slate" size="xs">
                  Current Type: <span className="font-semibold ml-1">{selectedColInfo.dtype}</span>
                </Badge>
                <Badge variant="blue" size="xs">
                  Semantic Role: <span className="font-semibold ml-1">{selectedColInfo.role}</span>
                </Badge>
              </div>
            )}
          </div>

          {/* Transformation Selection */}
          <div className="md:col-span-5 space-y-2">
            <label className="text-xs font-semibold text-foreground block">
              Transformation Action
            </label>
            <select
              value={selectedTransformType}
              onChange={(e) => {
                setSelectedTransformType(e.target.value);
                setColPreviewResult(null);
                setColPreviewError(null);
              }}
              className="w-full text-xs bg-surface-muted/40 border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:border-primary font-medium"
            >
              <optgroup label="Datatype Conversions">
                <option value="CONVERT_NUMERIC">Convert to Numeric / Float</option>
                <option value="CONVERT_INTEGER">Convert to Integer (Safe Check)</option>
                <option value="CONVERT_DATETIME">Convert to Datetime (ISO Parse)</option>
                <option value="NORMALIZE_BOOLEAN">Convert to Boolean</option>
                <option value="CONVERT_STRING">Convert to Text / String</option>
              </optgroup>
              <optgroup label="String Normalization">
                <option value="TRIM_WHITESPACE">Trim Leading / Trailing Whitespace</option>
                <option value="NORMALIZE_EMPTY_STRINGS">Normalize Empty Strings to Missing</option>
              </optgroup>
              <optgroup label="Missing-Value Strategies">
                <option value="IMPUTE_MEDIAN">Impute with Median (Numeric)</option>
                <option value="IMPUTE_MEAN">Impute with Mean (Numeric)</option>
                <option value="IMPUTE_MODE">Impute with Most Frequent / Mode</option>
                <option value="IMPUTE_UNKNOWN">Impute with 'Unknown' (Text)</option>
                <option value="IMPUTE_SPECIFIC_VALUE">Impute with Specific Constant Value</option>
                <option value="LEAVE_UNCHANGED">Leave Missing Unchanged</option>
              </optgroup>
            </select>

            {/* Custom Value Input (if specific value selected) */}
            {selectedTransformType === 'IMPUTE_SPECIFIC_VALUE' && (
              <div className="pt-1">
                <input
                  type="text"
                  placeholder="Enter constant value (e.g. 0.0 or N/A)..."
                  value={customTransformVal}
                  onChange={(e) => setCustomTransformVal(e.target.value)}
                  className="w-full text-xs bg-surface border border-border rounded-md px-3 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
                />
              </div>
            )}
          </div>

          {/* Action Trigger */}
          <div className="md:col-span-3 space-y-2 flex flex-col justify-end pt-5 md:pt-0">
            <span className="text-2xs text-muted-foreground hidden md:block">
              Simulate before applying
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={handlePreviewColumnTransform}
              disabled={colPreviewLoading || !selectedCol}
              leftIcon={<Eye className="w-3.5 h-3.5" />}
              className="w-full text-xs"
            >
              {colPreviewLoading ? 'Simulating...' : 'Preview Change'}
            </Button>
          </div>
        </div>

        {/* Dynamic Contextual Explanation */}
        <div className="p-3 bg-surface-muted/30 border border-border/60 rounded-lg text-xs flex items-start gap-2.5">
          <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <p className="text-muted-foreground text-xs leading-relaxed">
            {getTransformExplanation()}
          </p>
        </div>

        {/* Error Display */}
        {colPreviewError && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs flex items-start gap-2.5 text-rose-500">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-semibold block">Transformation Validation Error</span>
              <p className="text-2xs text-rose-600 dark:text-rose-400">{colPreviewError}</p>
            </div>
          </div>
        )}

        {/* Fractional Warning & Truncation Confirmation */}
        {colPreviewResult && colPreviewResult.fractional_loss_count > 0 && (
          <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs space-y-2 text-amber-600 dark:text-amber-400">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Fractional Truncation Notice</span>
                <p className="text-2xs mt-0.5">
                  Integer conversion would truncate fractional values across {colPreviewResult.fractional_loss_count} rows (e.g. 12.5 → 12).
                </p>
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer pt-1 text-2xs font-semibold text-foreground">
              <input
                type="checkbox"
                checked={allowFractional}
                onChange={(e) => setAllowFractional(e.target.checked)}
                className="rounded text-primary focus:ring-primary h-3.5 w-3.5 border-border bg-surface"
              />
              <span>Explicitly allow truncation of fractional values to integer</span>
            </label>
          </div>
        )}

        {/* Deterministic Preview Result Panel */}
        {colPreviewResult && colPreviewResult.is_valid && (
          <div className="p-4 bg-surface-muted/20 border border-primary/20 rounded-lg space-y-3.5">
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <span className="text-xs font-bold text-foreground">
                Conversion Preview: {colPreviewResult.column_name}
              </span>
              <Badge variant="green" size="xs">
                {colPreviewResult.target_type}
              </Badge>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Data Type</span>
                <span className="font-semibold text-foreground text-xs">
                  {colPreviewResult.original_dtype} → <span className="text-primary font-bold">{colPreviewResult.target_dtype}</span>
                </span>
              </div>
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Converted</span>
                <span className="font-bold text-emerald-500 text-xs">
                  {colPreviewResult.converted_count} rows
                </span>
              </div>
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Unparseable / Failed</span>
                <span className={`font-bold text-xs ${colPreviewResult.unparseable_count > 0 ? 'text-amber-500' : 'text-muted-foreground'}`}>
                  {colPreviewResult.unparseable_count} {colPreviewResult.unparseable_count > 0 ? '(coerced to null)' : ''}
                </span>
              </div>
              <div className="p-2.5 bg-surface border border-border rounded-md">
                <span className="text-2xs text-muted-foreground block">Missing Values</span>
                <span className="font-semibold text-foreground text-xs">
                  {colPreviewResult.original_missing_count} → {colPreviewResult.new_missing_count}
                </span>
              </div>
            </div>

            {/* Unparseable values badges */}
            {colPreviewResult.unparseable_samples && colPreviewResult.unparseable_samples.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap text-2xs pt-1">
                <span className="text-muted-foreground font-medium">Unparseable tokens coerced to null:</span>
                {colPreviewResult.unparseable_samples.slice(0, 5).map((s, idx) => (
                  <Badge key={idx} variant="amber" size="xs">
                    "{String(s)}"
                  </Badge>
                ))}
              </div>
            )}

            {/* Sample Changes Table */}
            {colPreviewResult.sample_changes && colPreviewResult.sample_changes.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <span className="text-2xs font-semibold text-foreground block">
                  Sample Value Changes (First {colPreviewResult.sample_changes.length} rows)
                </span>
                <div className="border border-border rounded-md overflow-hidden max-h-36 overflow-y-auto">
                  <table className="w-full text-2xs text-left">
                    <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                      <tr>
                        <th className="p-1.5">Row</th>
                        <th className="p-1.5">Before Value</th>
                        <th className="p-1.5">Cleaned / Target Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border font-mono">
                      {colPreviewResult.sample_changes.map((change, idx) => (
                        <tr key={idx} className="hover:bg-surface-muted/30">
                          <td className="p-1.5 text-muted-foreground font-sans">#{change.row_index}</td>
                          <td className="p-1.5 text-rose-500 line-through truncate max-w-[150px]">
                            {change.before_value === null ? 'NULL' : String(change.before_value)}
                          </td>
                          <td className="p-1.5 text-emerald-500 font-bold truncate max-w-[150px]">
                            {change.after_value === null ? 'NULL' : String(change.after_value)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Action Buttons for Previewed Transformation */}
            <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-border/60">
              <Button
                variant="secondary"
                size="xs"
                onClick={handleQueueCustomTransform}
                leftIcon={<PlusCircle className="w-3.5 h-3.5 text-primary" />}
                className="text-xs"
              >
                Add to Cleaning Plan
              </Button>
              <Button
                variant="primary"
                size="xs"
                onClick={handleApplySingleTransform}
                leftIcon={<Play className="w-3.5 h-3.5" />}
                className="text-xs"
              >
                Apply Transformation Directly
              </Button>
            </div>
          </div>
        )}

        {/* Queued Custom Transformations List */}
        {customTransformations.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-border">
            <span className="text-xs font-semibold text-foreground block">
              Queued User Transformations ({customTransformations.length})
            </span>
            <div className="flex flex-wrap gap-2">
              {customTransformations.map((t, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-2 p-2 bg-primary/5 border border-primary/20 rounded-md text-xs"
                >
                  <span className="font-semibold text-foreground font-mono">{t.column_name}</span>
                  <Badge variant="blue" size="xs">
                    {t.operation.replace(/_/g, ' ')}
                  </Badge>
                  {t.custom_value && (
                    <span className="text-2xs text-muted-foreground font-mono">val="{t.custom_value}"</span>
                  )}
                  <button
                    onClick={() => handleRemoveCustomTransform(t.column_name)}
                    className="text-muted-foreground hover:text-rose-500 focus:outline-none ml-1"
                    title="Remove transformation"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* 2.5 Multi-Valued Cells Card (Part 6.3) */}
      <Card className="p-5 border border-border/80 bg-surface shadow-xs space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-500/10 text-indigo-500 flex items-center justify-center shrink-0">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground">
                  Multi-Valued Cells
                </h3>
                <Badge variant="purple" size="xs">
                  Part 6.3
                </Badge>
                {mvCandidates.length > 0 && (
                  <Badge variant="blue" size="xs">
                    {mvCandidates.length} candidate{mvCandidates.length > 1 ? 's' : ''} detected
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Detect columns containing multiple logical values inside a single cell (e.g. "12,17", "Python;SQL;Java"). User-controlled split, row expansion, or keep as is.
              </p>
            </div>
          </div>

          <Button
            variant="secondary"
            size="xs"
            onClick={fetchMvCandidates}
            disabled={isLoadingMvCandidates}
            leftIcon={<RotateCcw className={`w-3.5 h-3.5 ${isLoadingMvCandidates ? 'animate-spin' : ''}`} />}
          >
            {isLoadingMvCandidates ? 'Scanning...' : 'Rescan Columns'}
          </Button>
        </div>

        {/* Global Feedback Banners */}
        {mvApplySuccess && (
          <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs flex items-start justify-between gap-3 text-emerald-600 dark:text-emerald-400">
            <div className="flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{mvApplySuccess}</span>
            </div>
            <button
              onClick={() => setMvApplySuccess(null)}
              className="text-emerald-600 dark:text-emerald-400 hover:text-foreground focus:outline-none"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {mvApplyError && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs flex items-start justify-between gap-3 text-rose-500">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{mvApplyError}</span>
            </div>
            <button
              onClick={() => setMvApplyError(null)}
              className="text-rose-500 hover:text-foreground focus:outline-none"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {mvCandidatesError && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs flex items-start gap-2.5 text-rose-500">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{mvCandidatesError}</span>
          </div>
        )}

        {/* Loading Spinner */}
        {isLoadingMvCandidates && (
          <div className="p-8 text-center space-y-2">
            <div className="w-6 h-6 mx-auto text-primary">
              <svg className="animate-spin w-6 h-6" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            </div>
            <p className="text-xs text-muted-foreground">Scanning dataset for multi-valued cell patterns...</p>
          </div>
        )}

        {/* Empty State */}
        {!isLoadingMvCandidates && mvCandidates.length === 0 && !mvCandidatesError && (
          <div className="p-6 bg-surface-muted/20 border border-border/60 rounded-lg text-center space-y-1.5">
            <div className="w-8 h-8 rounded-full bg-surface-muted text-muted-foreground flex items-center justify-center mx-auto">
              <Check className="w-4 h-4 text-emerald-500" />
            </div>
            <h4 className="text-xs font-bold text-foreground">No Multi-Valued Cells Detected</h4>
            <p className="text-2xs text-muted-foreground max-w-md mx-auto">
              All string and numeric columns have consistent scalar data formatting. Formatted numbers (e.g. "1,250.50") were verified and safely excluded.
            </p>
          </div>
        )}

        {/* Candidates List */}
        {!isLoadingMvCandidates && mvCandidates.length > 0 && (
          <div className="space-y-4">
            {mvCandidates.map((cand) => {
              const colName = cand.column_name;
              const currentAction = mvSelectedActions[colName] || 'SPLIT_COLUMNS';
              const currentDelim = mvCustomDelimiters[colName] ?? cand.detected_delimiter;
              const isPreviewingThis = activeMvCol === colName && mvPreviewLoading;
              const hasPreview = activeMvCol === colName && mvPreviewResult !== null;
              const previewErr = activeMvCol === colName ? mvPreviewError : null;

              return (
                <div
                  key={colName}
                  className="p-4 bg-surface border border-border rounded-lg space-y-4 transition-all hover:border-primary/40"
                >
                  {/* Candidate Header & Metadata */}
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-border/60">
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-foreground font-mono">
                          {colName}
                        </span>
                        <Badge variant="slate" size="xs">
                          {cand.column_dtype}
                        </Badge>
                        <Badge variant="blue" size="xs">
                          {cand.semantic_role}
                        </Badge>
                        <Badge
                          variant={cand.confidence === 'HIGH' ? 'green' : cand.confidence === 'MEDIUM' ? 'blue' : 'amber'}
                          size="xs"
                        >
                          {cand.confidence} Confidence
                        </Badge>
                        <Badge variant="purple" size="xs">
                          Rec: {cand.recommendation.replace('_', ' ')}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {cand.reason}
                      </p>
                    </div>

                    {/* Stats Badges */}
                    <div className="flex items-center gap-3 text-xs shrink-0 flex-wrap">
                      <div className="px-2.5 py-1 bg-surface-muted/40 rounded border border-border text-center">
                        <span className="text-2xs text-muted-foreground block">Affected Rows</span>
                        <span className="font-bold text-foreground">
                          {cand.affected_rows.toLocaleString()} ({cand.affected_percentage}%)
                        </span>
                      </div>
                      <div className="px-2.5 py-1 bg-surface-muted/40 rounded border border-border text-center">
                        <span className="text-2xs text-muted-foreground block">Tokens / Row</span>
                        <span className="font-bold text-foreground">
                          {cand.average_values_per_affected_row} avg (max {cand.max_values_per_row})
                        </span>
                      </div>
                      <div className="px-2.5 py-1 bg-surface-muted/40 rounded border border-border text-center">
                        <span className="text-2xs text-muted-foreground block">Delimiter</span>
                        <span className="font-mono font-bold text-primary">
                          '{cand.detected_delimiter}'
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Examples Pill List */}
                  {cand.examples && cand.examples.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-2xs font-semibold text-muted-foreground block">
                        Representative Sample Values:
                      </span>
                      <div className="flex items-center gap-2 flex-wrap">
                        {cand.examples.map((ex, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 bg-surface-muted border border-border text-foreground font-mono text-2xs rounded truncate max-w-[240px]"
                            title={ex}
                          >
                            {ex}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* User Control Form: Action Selector & Delimiter Override */}
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end pt-2 bg-surface-muted/20 p-3 rounded-md border border-border/60">
                    {/* Action Selector */}
                    <div className="sm:col-span-6 space-y-1">
                      <label className="text-2xs font-semibold text-foreground block">
                        Choose Action:
                      </label>
                      <div className="grid grid-cols-3 gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setMvSelectedActions((prev) => ({ ...prev, [colName]: 'KEEP' }));
                            if (activeMvCol === colName) setMvPreviewResult(null);
                          }}
                          className={`px-2 py-1.5 text-xs rounded border transition-colors font-medium text-center ${
                            currentAction === 'KEEP'
                              ? 'bg-slate-700 text-white border-slate-600 shadow-2xs font-bold'
                              : 'bg-surface border-border text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Keep As Is
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setMvSelectedActions((prev) => ({ ...prev, [colName]: 'SPLIT_COLUMNS' }));
                            if (activeMvCol === colName) setMvPreviewResult(null);
                          }}
                          className={`px-2 py-1.5 text-xs rounded border transition-colors font-medium text-center ${
                            currentAction === 'SPLIT_COLUMNS'
                              ? 'bg-primary text-primary-foreground border-primary shadow-2xs font-bold'
                              : 'bg-surface border-border text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Split to Columns
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setMvSelectedActions((prev) => ({ ...prev, [colName]: 'EXPAND_ROWS' }));
                            if (activeMvCol === colName) setMvPreviewResult(null);
                          }}
                          className={`px-2 py-1.5 text-xs rounded border transition-colors font-medium text-center ${
                            currentAction === 'EXPAND_ROWS'
                              ? 'bg-amber-600 text-white border-amber-600 shadow-2xs font-bold'
                              : 'bg-surface border-border text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          Expand into Rows
                        </button>
                      </div>
                    </div>

                    {/* Delimiter Override */}
                    <div className="sm:col-span-3 space-y-1">
                      <label className="text-2xs font-semibold text-foreground block">
                        Delimiter:
                      </label>
                      <input
                        type="text"
                        value={currentDelim}
                        onChange={(e) => {
                          setMvCustomDelimiters((prev) => ({ ...prev, [colName]: e.target.value }));
                          if (activeMvCol === colName) setMvPreviewResult(null);
                        }}
                        className="w-full text-xs font-mono bg-surface border border-border rounded px-2.5 py-1.5 text-foreground focus:outline-none focus:border-primary"
                        placeholder="e.g. , or ; or |"
                      />
                    </div>

                    {/* Preview Button */}
                    <div className="sm:col-span-3">
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => handlePreviewMultiValue(colName)}
                        disabled={isPreviewingThis || mvApplyLoading}
                        leftIcon={<Eye className="w-3.5 h-3.5" />}
                        className="w-full text-xs"
                      >
                        {isPreviewingThis ? 'Simulating...' : 'Preview Change'}
                      </Button>
                    </div>
                  </div>

                  {/* Preview Error */}
                  {previewErr && (
                    <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-md text-xs text-rose-500 flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold block">Preview Failed</span>
                        <p className="text-2xs text-rose-600 dark:text-rose-400">{previewErr}</p>
                      </div>
                    </div>
                  )}

                  {/* Preview Result Display */}
                  {hasPreview && mvPreviewResult && (
                    <div className="p-4 bg-surface-muted/30 border border-primary/30 rounded-lg space-y-4">
                      {/* Preview Top Header */}
                      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-border/80">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-foreground">
                            Preview: {mvPreviewResult.action.replace('_', ' ')}
                          </span>
                          <Badge variant="blue" size="xs">
                            Delimiter: '{mvPreviewResult.delimiter_used}'
                          </Badge>
                          <Badge variant="slate" size="xs">
                            {mvPreviewResult.affected_rows} rows affected
                          </Badge>
                        </div>
                        <button
                          onClick={() => setMvPreviewResult(null)}
                          className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 focus:outline-none"
                        >
                          <X className="w-3.5 h-3.5" />
                          <span>Close Preview</span>
                        </button>
                      </div>

                      {/* Expanding Warning Notice (Mandatory Requirement) */}
                      {mvPreviewResult.action === 'EXPAND_ROWS' && (
                        <div className="p-3 bg-amber-500/15 border border-amber-500/40 rounded-md text-xs flex items-start gap-2.5 text-amber-700 dark:text-amber-300">
                          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
                          <div className="space-y-0.5">
                            <span className="font-bold block">Notice on Context Duplication:</span>
                            <p className="text-2xs font-semibold">
                              Expanding values duplicates the other fields in affected rows.
                            </p>
                          </div>
                        </div>
                      )}

                      {/* Preview Metrics */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                        <div className="p-2.5 bg-surface border border-border rounded-md">
                          <span className="text-2xs text-muted-foreground block">Row Count</span>
                          <span className="font-bold text-foreground text-xs">
                            {mvPreviewResult.original_row_count.toLocaleString()} →{' '}
                            <span className={mvPreviewResult.rows_added > 0 ? 'text-amber-500 font-bold' : 'text-foreground'}>
                              {mvPreviewResult.resulting_row_count.toLocaleString()}
                            </span>
                            {mvPreviewResult.rows_added > 0 && (
                              <span className="text-2xs text-amber-500 ml-1 font-normal">
                                (+{mvPreviewResult.rows_added})
                              </span>
                            )}
                          </span>
                        </div>

                        <div className="p-2.5 bg-surface border border-border rounded-md">
                          <span className="text-2xs text-muted-foreground block">Column Count</span>
                          <span className="font-bold text-foreground text-xs">
                            {mvPreviewResult.original_column_count} →{' '}
                            <span className={mvPreviewResult.resulting_column_count !== mvPreviewResult.original_column_count ? 'text-primary font-bold' : 'text-foreground'}>
                              {mvPreviewResult.resulting_column_count}
                            </span>
                          </span>
                        </div>

                        <div className="p-2.5 bg-surface border border-border rounded-md">
                          <span className="text-2xs text-muted-foreground block">Affected Records</span>
                          <span className="font-bold text-emerald-500 text-xs">
                            {mvPreviewResult.affected_rows} rows
                          </span>
                        </div>

                        <div className="p-2.5 bg-surface border border-border rounded-md">
                          <span className="text-2xs text-muted-foreground block">Generated Columns</span>
                          <span className="font-bold text-primary text-xs truncate block">
                            {mvPreviewResult.generated_columns.length > 0
                              ? mvPreviewResult.generated_columns.join(', ')
                              : 'None'}
                          </span>
                        </div>
                      </div>

                      {/* Sample Before / After Table */}
                      {mvPreviewResult.sample_before_after && mvPreviewResult.sample_before_after.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-2xs font-semibold text-muted-foreground block">
                            Sample Changes (First {mvPreviewResult.sample_before_after.length} affected records):
                          </span>
                          <div className="overflow-x-auto border border-border rounded-md bg-surface">
                            {mvPreviewResult.action === 'SPLIT_COLUMNS' ? (
                              <table className="w-full text-2xs text-left">
                                <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                                  <tr>
                                    <th className="p-2 font-medium">Row</th>
                                    <th className="p-2 font-medium">Original Value ({colName})</th>
                                    {mvPreviewResult.generated_columns.map((gCol) => (
                                      <th key={gCol} className="p-2 font-medium font-mono text-primary">
                                        {gCol}
                                      </th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-border/60">
                                  {mvPreviewResult.sample_before_after.map((sample: any, sIdx: number) => (
                                    <tr key={sIdx} className="hover:bg-surface-muted/30">
                                      <td className="p-2 font-mono text-muted-foreground">
                                        #{sample.row_index}
                                      </td>
                                      <td className="p-2 font-mono text-rose-500 line-through truncate max-w-[160px]">
                                        {String(sample.before)}
                                      </td>
                                      {mvPreviewResult.generated_columns.map((gCol) => (
                                        <td key={gCol} className="p-2 font-mono text-emerald-500 font-bold truncate max-w-[140px]">
                                          {sample.after?.[gCol] !== null && sample.after?.[gCol] !== undefined
                                            ? String(sample.after[gCol])
                                            : <span className="text-muted-foreground font-normal italic">null</span>}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : mvPreviewResult.action === 'EXPAND_ROWS' ? (
                              <table className="w-full text-2xs text-left">
                                <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                                  <tr>
                                    <th className="p-2 font-medium">Original Row</th>
                                    <th className="p-2 font-medium">Original Cell Value</th>
                                    <th className="p-2 font-medium">Expanded Resulting Rows</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-border/60">
                                  {mvPreviewResult.sample_before_after.map((sample: any, sIdx: number) => (
                                    <tr key={sIdx} className="hover:bg-surface-muted/30">
                                      <td className="p-2 font-mono text-muted-foreground">
                                        #{sample.original_row_index}
                                      </td>
                                      <td className="p-2 font-mono text-amber-500 font-medium truncate max-w-[180px]">
                                        {String(sample.before_value)}
                                      </td>
                                      <td className="p-2 font-mono">
                                        <div className="flex flex-col gap-1">
                                          {sample.after_rows?.map((row: any, rIdx: number) => (
                                            <div key={rIdx} className="flex items-center gap-2">
                                              <Badge variant="green" size="xs">Row +{rIdx + 1}</Badge>
                                              <span className="text-emerald-500 font-bold">{colName}: "{row[colName]}"</span>
                                              <span className="text-2xs text-muted-foreground">
                                                (context duplicated)
                                              </span>
                                            </div>
                                          ))}
                                        </div>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : (
                              <div className="p-3 text-2xs text-muted-foreground text-center">
                                Keep As Is selected. Data will remain unmodified.
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Apply Transformation Button */}
                      <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                        <Button
                          variant="secondary"
                          size="xs"
                          onClick={() => setMvPreviewResult(null)}
                        >
                          Dismiss
                        </Button>
                        <Button
                          variant="primary"
                          size="xs"
                          onClick={() => handleApplyMultiValue(colName)}
                          disabled={mvApplyLoading}
                          leftIcon={<Play className="w-3.5 h-3.5" />}
                          className="text-xs"
                        >
                          {mvApplyLoading ? 'Applying Transformation...' : 'Apply Transformation'}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ========================================================================= */}
      {/* PART 6.4 — STRUCTURAL CLEANING & USER-CONTROLLED SEMANTIC ROLES          */}
      {/* ========================================================================= */}
      <Card className="p-5 border border-primary/20 bg-surface/80 backdrop-blur-sm space-y-5">
        {/* Section Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-primary/10 text-primary shrink-0">
              <SlidersHorizontal className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-bold text-foreground">
                  Structural Cleaning & Semantic Roles
                </h3>
                <Badge variant="blue" size="xs">
                  Deterministic · Part 6.4
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Drop columns, filter rows with structured multi-conditions, remove duplicate rows, and authoritatively override semantic roles.
              </p>
            </div>
          </div>

          {/* Subtab Navigation Pills */}
          <div className="flex items-center gap-1.5 p-1 bg-surface-muted/60 rounded-lg border border-border text-xs flex-wrap">
            <button
              type="button"
              onClick={() => setActiveStructTab('RECOMMENDATIONS')}
              className={`px-2.5 py-1 rounded-md transition-colors font-medium flex items-center gap-1.5 ${
                activeStructTab === 'RECOMMENDATIONS'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Recommendations</span>
              {structRecs.length > 0 && (
                <span className="px-1.5 py-0.2 bg-white/20 rounded-full text-2xs font-bold">
                  {structRecs.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveStructTab('DROP_COLUMNS')}
              className={`px-2.5 py-1 rounded-md transition-colors font-medium flex items-center gap-1.5 ${
                activeStructTab === 'DROP_COLUMNS'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Columns className="w-3.5 h-3.5" />
              <span>Drop Columns</span>
              {selectedDropCols.length > 0 && (
                <span className="px-1.5 py-0.2 bg-white/20 rounded-full text-2xs font-bold">
                  {selectedDropCols.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveStructTab('FILTER_ROWS')}
              className={`px-2.5 py-1 rounded-md transition-colors font-medium flex items-center gap-1.5 ${
                activeStructTab === 'FILTER_ROWS'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Filter className="w-3.5 h-3.5" />
              <span>Filter Rows</span>
              {filterConditions.length > 0 && (
                <span className="px-1.5 py-0.2 bg-white/20 rounded-full text-2xs font-bold">
                  {filterConditions.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveStructTab('DUPLICATES')}
              className={`px-2.5 py-1 rounded-md transition-colors font-medium flex items-center gap-1.5 ${
                activeStructTab === 'DUPLICATES'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Copy className="w-3.5 h-3.5" />
              <span>Duplicates</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveStructTab('SEMANTIC_ROLES')}
              className={`px-2.5 py-1 rounded-md transition-colors font-medium flex items-center gap-1.5 ${
                activeStructTab === 'SEMANTIC_ROLES'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Tag className="w-3.5 h-3.5" />
              <span>Semantic Roles</span>
            </button>
          </div>
        </div>

        {/* ------------------------------------------------------------------- */}
        {/* SUBTAB 1: STRUCTURAL QUALITY RECOMMENDATIONS                        */}
        {/* ------------------------------------------------------------------- */}
        {activeStructTab === 'RECOMMENDATIONS' && (
          <div className="space-y-4">
            {structRecsError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{structRecsError}</span>
              </div>
            )}

            {isLoadingStructRecs && (
              <div className="p-8 text-center space-y-2">
                <div className="w-6 h-6 mx-auto text-primary">
                  <svg className="animate-spin w-6 h-6" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                </div>
                <p className="text-xs text-muted-foreground">Evaluating structural anomalies and column statistics...</p>
              </div>
            )}

            {!isLoadingStructRecs && structRecs.length === 0 && !structRecsError && (
              <div className="p-6 bg-surface-muted/20 border border-border/60 rounded-lg text-center space-y-1.5">
                <div className="w-8 h-8 rounded-full bg-surface-muted text-muted-foreground flex items-center justify-center mx-auto">
                  <Check className="w-4 h-4 text-emerald-500" />
                </div>
                <h4 className="text-xs font-bold text-foreground">No Structural Anomalies Detected</h4>
                <p className="text-2xs text-muted-foreground max-w-md mx-auto">
                  All columns possess healthy variance, manageable missingness, and distinct semantic profiles. No automatic drop actions required.
                </p>
              </div>
            )}

            {!isLoadingStructRecs && structRecs.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {structRecs.map((rec) => {
                  const issueBadgeVariant: 'red' | 'amber' | 'purple' | 'blue' =
                    rec.issue_type === 'HIGH_MISSINGNESS'
                      ? 'red'
                      : rec.issue_type === 'CONSTANT_COLUMN'
                      ? 'amber'
                      : rec.issue_type === 'LIKELY_IDENTIFIER'
                      ? 'purple'
                      : 'blue';

                  return (
                    <div
                      key={rec.recommendation_id}
                      className="p-4 bg-surface border border-border rounded-lg space-y-3 hover:border-primary/40 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <Badge variant={issueBadgeVariant} size="xs">
                              {rec.issue_type.replace('_', ' ')}
                            </Badge>
                            {rec.column_name && (
                              <span className="font-mono font-bold text-foreground text-xs px-2 py-0.5 bg-surface-muted rounded border border-border">
                                {rec.column_name}
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-semibold text-foreground">
                            {rec.reason}
                          </p>
                        </div>
                      </div>

                      {/* Evidence List */}
                      {rec.evidence && rec.evidence.length > 0 && (
                        <div className="space-y-1 bg-surface-muted/40 p-2.5 rounded border border-border/60 text-2xs text-muted-foreground">
                          {rec.evidence.map((ev, idx) => (
                            <div key={idx} className="flex items-center gap-1.5">
                              <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                              <span>{ev}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Action Buttons */}
                      <div className="flex items-center gap-2 pt-1 border-t border-border/60 flex-wrap">
                        <span className="text-2xs font-semibold text-muted-foreground mr-1">
                          Actions:
                        </span>

                        {rec.allowed_actions.includes('DROP_COLUMN') && rec.column_name && (
                          <Button
                            variant="secondary"
                            size="xs"
                            onClick={() => {
                              setSelectedDropCols([rec.column_name!]);
                              setActiveStructTab('DROP_COLUMNS');
                              handlePreviewDropColumns();
                            }}
                            className="text-xs text-rose-500 hover:text-rose-600 border-rose-500/30"
                          >
                            Drop Column
                          </Button>
                        )}

                        {rec.allowed_actions.includes('MARK_IDENTIFIER') && rec.column_name && (
                          <Button
                            variant="secondary"
                            size="xs"
                            onClick={() => {
                              setSelectedRoleCol(rec.column_name!);
                              setSelectedRoleValue('IDENTIFIER');
                              setActiveStructTab('SEMANTIC_ROLES');
                              handlePreviewSemanticRoleOverride(rec.column_name!, 'IDENTIFIER');
                            }}
                            className="text-xs text-purple-500 hover:text-purple-600 border-purple-500/30"
                          >
                            Mark as Identifier
                          </Button>
                        )}

                        {rec.allowed_actions.includes('REMOVE_DUPLICATES') && (
                          <Button
                            variant="secondary"
                            size="xs"
                            onClick={() => {
                              setActiveStructTab('DUPLICATES');
                              handlePreviewRemoveDuplicates();
                            }}
                            className="text-xs text-amber-500 hover:text-amber-600 border-amber-500/30"
                          >
                            Remove Duplicates
                          </Button>
                        )}

                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            setStructRecs((prev) => prev.filter((r) => r.recommendation_id !== rec.recommendation_id));
                          }}
                          className="text-2xs text-muted-foreground"
                        >
                          Keep
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------- */}
        {/* SUBTAB 2: COLUMN DROPPING                                           */}
        {/* ------------------------------------------------------------------- */}
        {activeStructTab === 'DROP_COLUMNS' && (
          <div className="space-y-4">
            {dropApplySuccess && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-500 flex items-center justify-between">
                <span>{dropApplySuccess}</span>
                <button onClick={() => setDropApplySuccess(null)} className="text-emerald-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {dropApplyError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{dropApplyError}</span>
                <button onClick={() => setDropApplyError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {dropPreviewError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{dropPreviewError}</span>
                <button onClick={() => setDropPreviewError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-foreground">
                  Select Columns to Remove ({selectedDropCols.length} of {availableColumns.length} selected):
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedDropCols([])}
                    className="text-2xs text-muted-foreground hover:text-foreground"
                  >
                    Clear All
                  </button>
                </div>
              </div>

              {/* Checkbox Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 p-3.5 bg-surface-muted/20 border border-border rounded-lg max-h-56 overflow-y-auto">
                {availableColumns.map((colName) => {
                  const isChecked = selectedDropCols.includes(colName);
                  return (
                    <label
                      key={colName}
                      className={`flex items-center gap-2.5 p-2 rounded-md border cursor-pointer transition-colors text-xs ${
                        isChecked
                          ? 'bg-rose-500/10 border-rose-500/40 text-rose-600 dark:text-rose-400 font-semibold'
                          : 'bg-surface border-border text-foreground hover:border-primary/40'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => handleToggleDropCol(colName)}
                        className="rounded border-border text-rose-600 focus:ring-rose-500 h-3.5 w-3.5"
                      />
                      <span className="truncate font-mono">{colName}</span>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Preview Trigger */}
            <div className="flex items-center justify-between gap-3 pt-2">
              <p className="text-2xs text-muted-foreground">
                Raw dataset is never modified. Preview simulates removal on a deep copy.
              </p>
              <Button
                variant="primary"
                size="sm"
                onClick={handlePreviewDropColumns}
                disabled={selectedDropCols.length === 0 || dropPreviewLoading || dropApplyLoading}
                leftIcon={<Eye className="w-3.5 h-3.5" />}
                className="text-xs shrink-0"
              >
                {dropPreviewLoading ? 'Simulating...' : `Preview Dropping (${selectedDropCols.length})`}
              </Button>
            </div>

            {/* Preview Results Display */}
            {dropPreviewResult && (
              <div className="p-4 bg-surface-muted/30 border border-primary/30 rounded-lg space-y-4 animate-in fade-in duration-150">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-foreground">
                      Column Drop Preview
                    </span>
                    <Badge variant="red" size="xs">
                      {dropPreviewResult.columns_to_drop.length} Columns To Drop
                    </Badge>
                  </div>
                  <button
                    onClick={() => setDropPreviewResult(null)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Columns Before</span>
                    <span className="font-bold text-foreground text-sm">
                      {dropPreviewResult.original_column_count}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Columns After</span>
                    <span className="font-bold text-rose-500 text-sm">
                      {dropPreviewResult.resulting_column_count}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Rows Preserved</span>
                    <span className="font-bold text-emerald-500 text-sm">
                      {dropPreviewResult.resulting_row_count.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Net Dropped</span>
                    <span className="font-bold text-foreground text-sm">
                      -{dropPreviewResult.columns_to_drop.length}
                    </span>
                  </div>
                </div>

                {/* Dropped Columns List */}
                <div className="space-y-1.5">
                  <span className="text-2xs font-semibold text-muted-foreground block">
                    Dropped Columns:
                  </span>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {dropPreviewResult.columns_to_drop.map((c) => (
                      <Badge key={c} variant="red" size="xs">
                        {c}
                      </Badge>
                    ))}
                  </div>
                </div>

                {/* Confirmation Apply Button */}
                <div className="flex items-center justify-between pt-3 border-t border-border/60">
                  <span className="text-2xs text-muted-foreground">
                    Explicit confirmation required to apply changes to in-memory cleaned dataset.
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="xs"
                      onClick={() => setDropPreviewResult(null)}
                    >
                      Dismiss
                    </Button>
                    <Button
                      variant="primary"
                      size="xs"
                      onClick={handleApplyDropColumns}
                      disabled={dropApplyLoading}
                      leftIcon={<Play className="w-3.5 h-3.5" />}
                      className="text-xs bg-rose-600 hover:bg-rose-700 text-white"
                    >
                      {dropApplyLoading ? 'Dropping Columns...' : 'Confirm & Apply Column Drop'}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------- */}
        {/* SUBTAB 3: ROW FILTERING / REMOVAL                                   */}
        {/* ------------------------------------------------------------------- */}
        {activeStructTab === 'FILTER_ROWS' && (
          <div className="space-y-4">
            {filterApplySuccess && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-500 flex items-center justify-between">
                <span>{filterApplySuccess}</span>
                <button onClick={() => setFilterApplySuccess(null)} className="text-emerald-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {filterApplyError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{filterApplyError}</span>
                <button onClick={() => setFilterApplyError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {filterPreviewError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{filterPreviewError}</span>
                <button onClick={() => setFilterPreviewError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-foreground">
                  Structured Filter Conditions (Rows matching will be REMOVED):
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-muted-foreground font-medium">Connector:</span>
                  <div className="flex rounded-md bg-surface-muted p-0.5 border border-border">
                    <button
                      type="button"
                      onClick={() => { setFilterLogicalOp('AND'); setFilterPreviewResult(null); }}
                      className={`px-2 py-0.5 text-2xs font-bold rounded ${
                        filterLogicalOp === 'AND' ? 'bg-primary text-white shadow-2xs' : 'text-muted-foreground'
                      }`}
                    >
                      AND
                    </button>
                    <button
                      type="button"
                      onClick={() => { setFilterLogicalOp('OR'); setFilterPreviewResult(null); }}
                      className={`px-2 py-0.5 text-2xs font-bold rounded ${
                        filterLogicalOp === 'OR' ? 'bg-amber-600 text-white shadow-2xs' : 'text-muted-foreground'
                      }`}
                    >
                      OR
                    </button>
                  </div>
                </div>
              </div>

              {/* Conditions Builder List */}
              <div className="space-y-2.5">
                {filterConditions.map((cond, idx) => {
                  const isMissingOp = cond.operator.includes('missing') || cond.operator.includes('null');
                  return (
                    <div
                      key={idx}
                      className="grid grid-cols-1 sm:grid-cols-12 gap-2.5 items-center p-3 bg-surface-muted/20 border border-border rounded-lg"
                    >
                      {/* Column Selector */}
                      <div className="sm:col-span-4">
                        <select
                          value={cond.column}
                          onChange={(e) => handleUpdateCondition(idx, 'column', e.target.value)}
                          className="w-full text-xs font-mono bg-surface border border-border rounded-md px-2.5 py-1.5 text-foreground focus:outline-none focus:border-primary"
                        >
                          {availableColumns.map((col) => (
                            <option key={col} value={col}>
                              {col}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Operator Dropdown */}
                      <div className="sm:col-span-4">
                        <select
                          value={cond.operator}
                          onChange={(e) => handleUpdateCondition(idx, 'operator', e.target.value)}
                          className="w-full text-xs bg-surface border border-border rounded-md px-2.5 py-1.5 text-foreground focus:outline-none focus:border-primary cursor-pointer"
                        >
                          <option value="equals">equals (=)</option>
                          <option value="not equals">not equals (!=)</option>
                          <option value="greater than">greater than (&gt;)</option>
                          <option value="less than">less than (&lt;)</option>
                          <option value="greater than or equal">greater than or equal (&gt;=)</option>
                          <option value="less than or equal">less than or equal (&lt;=)</option>
                          <option value="is missing">is missing (NULL)</option>
                          <option value="is not missing">is not missing (Not NULL)</option>
                          <option value="contains">contains (substring)</option>
                        </select>
                      </div>

                      {/* Value Input */}
                      <div className="sm:col-span-3">
                        <input
                          type="text"
                          value={cond.value || ''}
                          disabled={isMissingOp}
                          onChange={(e) => handleUpdateCondition(idx, 'value', e.target.value)}
                          placeholder={isMissingOp ? 'N/A (missingness)' : 'Comparison value'}
                          className={`w-full text-xs bg-surface border border-border rounded-md px-2.5 py-1.5 text-foreground focus:outline-none focus:border-primary ${
                            isMissingOp ? 'opacity-40 cursor-not-allowed' : ''
                          }`}
                        />
                      </div>

                      {/* Delete Button */}
                      <div className="sm:col-span-1 flex justify-end">
                        <button
                          type="button"
                          disabled={filterConditions.length <= 1}
                          onClick={() => handleRemoveCondition(idx)}
                          className="p-1.5 text-muted-foreground hover:text-rose-500 disabled:opacity-30 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Add Condition & Preview Action */}
              <div className="flex items-center justify-between gap-3 pt-2">
                <Button
                  variant="secondary"
                  size="xs"
                  onClick={handleAddCondition}
                  leftIcon={<PlusCircle className="w-3.5 h-3.5" />}
                  className="text-xs"
                >
                  Add Condition
                </Button>

                <Button
                  variant="primary"
                  size="sm"
                  onClick={handlePreviewFilterRows}
                  disabled={filterPreviewLoading || filterApplyLoading}
                  leftIcon={<Eye className="w-3.5 h-3.5" />}
                  className="text-xs shrink-0"
                >
                  {filterPreviewLoading ? 'Simulating...' : 'Preview Row Removal'}
                </Button>
              </div>
            </div>

            {/* Preview Results Display */}
            {filterPreviewResult && (
              <div className="p-4 bg-surface-muted/30 border border-primary/30 rounded-lg space-y-4 animate-in fade-in duration-150">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-foreground">
                      Row Removal Simulation
                    </span>
                    <Badge variant={filterPreviewResult.rows_removed > 0 ? 'amber' : 'slate'} size="xs">
                      {filterPreviewResult.rows_removed.toLocaleString()} Rows Removed
                    </Badge>
                  </div>
                  <button
                    onClick={() => setFilterPreviewResult(null)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Rows Before</span>
                    <span className="font-bold text-foreground text-sm">
                      {filterPreviewResult.original_row_count.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Rows After Removal</span>
                    <span className="font-bold text-emerald-500 text-sm">
                      {filterPreviewResult.resulting_row_count.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Rows Filtered Out</span>
                    <span className="font-bold text-rose-500 text-sm">
                      -{filterPreviewResult.rows_removed.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Sample Matching Rows Table */}
                {filterPreviewResult.sample_matching_rows && filterPreviewResult.sample_matching_rows.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-2xs font-semibold text-rose-500 block">
                      Sample Matching Records (Will be removed):
                    </span>
                    <div className="overflow-x-auto border border-border rounded-md bg-surface max-h-36 overflow-y-auto">
                      <table className="w-full text-2xs text-left font-mono">
                        <thead className="bg-surface-muted text-muted-foreground border-b border-border sticky top-0">
                          <tr>
                            {Object.keys(filterPreviewResult.sample_matching_rows[0]).map((k) => (
                              <th key={k} className="p-1.5 font-medium">{k}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/60">
                          {filterPreviewResult.sample_matching_rows.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-rose-500/10">
                              {Object.values(row).map((v, cIdx) => (
                                <td key={cIdx} className="p-1.5 text-rose-500 truncate max-w-[120px]">
                                  {v === null ? 'NULL' : String(v)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Confirmation Apply Button */}
                <div className="flex items-center justify-between pt-3 border-t border-border/60">
                  <span className="text-2xs text-muted-foreground">
                    Deterministic condition execution. Deep copy will be updated.
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="xs"
                      onClick={() => setFilterPreviewResult(null)}
                    >
                      Dismiss
                    </Button>
                    <Button
                      variant="primary"
                      size="xs"
                      onClick={handleApplyFilterRows}
                      disabled={filterApplyLoading}
                      leftIcon={<Play className="w-3.5 h-3.5" />}
                      className="text-xs bg-rose-600 hover:bg-rose-700 text-white"
                    >
                      {filterApplyLoading ? 'Filtering Rows...' : 'Confirm & Apply Row Removal'}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------- */}
        {/* SUBTAB 4: DUPLICATE ROW REMOVAL                                     */}
        {/* ------------------------------------------------------------------- */}
        {activeStructTab === 'DUPLICATES' && (
          <div className="space-y-4">
            {dupApplySuccess && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-500 flex items-center justify-between">
                <span>{dupApplySuccess}</span>
                <button onClick={() => setDupApplySuccess(null)} className="text-emerald-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {dupApplyError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{dupApplyError}</span>
                <button onClick={() => setDupApplyError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {dupPreviewError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{dupPreviewError}</span>
                <button onClick={() => setDupPreviewError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <div className="p-4 bg-surface-muted/20 border border-border rounded-lg space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <h4 className="text-xs font-bold text-foreground">Exact Duplicate Rows Detection</h4>
                  <p className="text-2xs text-muted-foreground mt-0.5">
                    Identifies records where all column values are completely identical.
                  </p>
                </div>

                {/* Strategy Selector */}
                <div className="flex items-center gap-2">
                  <span className="text-2xs font-semibold text-muted-foreground">Keep Strategy:</span>
                  <div className="flex rounded-md bg-surface p-0.5 border border-border">
                    <button
                      type="button"
                      onClick={() => { setDupKeepStrategy('first'); setDupPreviewResult(null); }}
                      className={`px-3 py-1 text-xs rounded transition-colors ${
                        dupKeepStrategy === 'first' ? 'bg-primary text-white font-bold shadow-2xs' : 'text-muted-foreground'
                      }`}
                    >
                      Keep First
                    </button>
                    <button
                      type="button"
                      onClick={() => { setDupKeepStrategy('last'); setDupPreviewResult(null); }}
                      className={`px-3 py-1 text-xs rounded transition-colors ${
                        dupKeepStrategy === 'last' ? 'bg-primary text-white font-bold shadow-2xs' : 'text-muted-foreground'
                      }`}
                    >
                      Keep Last
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handlePreviewRemoveDuplicates}
                  disabled={dupPreviewLoading || dupApplyLoading}
                  leftIcon={<Eye className="w-3.5 h-3.5" />}
                  className="text-xs"
                >
                  {dupPreviewLoading ? 'Scanning...' : 'Preview Duplicate Removal'}
                </Button>
              </div>
            </div>

            {/* Duplicate Preview Results Display */}
            {dupPreviewResult && (
              <div className="p-4 bg-surface-muted/30 border border-primary/30 rounded-lg space-y-4 animate-in fade-in duration-150">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-foreground">
                      Duplicate Removal Simulation
                    </span>
                    <Badge variant={dupPreviewResult.rows_removed > 0 ? 'amber' : 'green'} size="xs">
                      {dupPreviewResult.rows_removed} Duplicates Found (Keep: {dupPreviewResult.keep_strategy})
                    </Badge>
                  </div>
                  <button
                    onClick={() => setDupPreviewResult(null)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Rows Before</span>
                    <span className="font-bold text-foreground text-sm">
                      {dupPreviewResult.original_row_count.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Rows After Deduplication</span>
                    <span className="font-bold text-emerald-500 text-sm">
                      {dupPreviewResult.resulting_row_count.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md">
                    <span className="text-2xs text-muted-foreground block">Duplicates Removed</span>
                    <span className="font-bold text-rose-500 text-sm">
                      -{dupPreviewResult.rows_removed.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Sample Duplicate Rows Table */}
                {dupPreviewResult.sample_duplicate_rows && dupPreviewResult.sample_duplicate_rows.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-2xs font-semibold text-muted-foreground block">
                      Sample Duplicate Records (First {dupPreviewResult.sample_duplicate_rows.length} rows):
                    </span>
                    <div className="overflow-x-auto border border-border rounded-md bg-surface max-h-36 overflow-y-auto">
                      <table className="w-full text-2xs text-left font-mono">
                        <thead className="bg-surface-muted text-muted-foreground border-b border-border sticky top-0">
                          <tr>
                            {Object.keys(dupPreviewResult.sample_duplicate_rows[0]).map((k) => (
                              <th key={k} className="p-1.5 font-medium">{k}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/60">
                          {dupPreviewResult.sample_duplicate_rows.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-surface-muted/30">
                              {Object.values(row).map((v, cIdx) => (
                                <td key={cIdx} className="p-1.5 truncate max-w-[120px]">
                                  {v === null ? 'NULL' : String(v)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Confirmation Apply Button */}
                <div className="flex items-center justify-between pt-3 border-t border-border/60">
                  <span className="text-2xs text-muted-foreground">
                    Deduplication will retain the {dupPreviewResult.keep_strategy} occurrence of each duplicate record.
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="xs"
                      onClick={() => setDupPreviewResult(null)}
                    >
                      Dismiss
                    </Button>
                    <Button
                      variant="primary"
                      size="xs"
                      onClick={handleApplyRemoveDuplicates}
                      disabled={dupApplyLoading || dupPreviewResult.rows_removed === 0}
                      leftIcon={<Play className="w-3.5 h-3.5" />}
                      className="text-xs bg-amber-600 hover:bg-amber-700 text-white"
                    >
                      {dupApplyLoading ? 'Deduplicating...' : 'Confirm & Remove Duplicates'}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------- */}
        {/* SUBTAB 5: USER-CONTROLLED SEMANTIC ROLE OVERRIDES                   */}
        {/* ------------------------------------------------------------------- */}
        {activeStructTab === 'SEMANTIC_ROLES' && (
          <div className="space-y-4">
            {roleApplySuccess && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-500 flex items-center justify-between">
                <span>{roleApplySuccess}</span>
                <button onClick={() => setRoleApplySuccess(null)} className="text-emerald-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {roleApplyError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{roleApplyError}</span>
                <button onClick={() => setRoleApplyError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {rolePreviewError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-500 flex items-center justify-between">
                <span>{rolePreviewError}</span>
                <button onClick={() => setRolePreviewError(null)} className="text-rose-500 hover:text-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Informational Guidance on Physical Type vs Semantic Role Separation */}
            <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-xs flex items-start gap-2.5 text-blue-600 dark:text-blue-400">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold block">Datatype vs. Semantic Role Distinction</span>
                <p className="text-2xs text-muted-foreground leading-relaxed">
                  Physical datatypes (e.g. <code className="text-primary font-mono">int64</code>, <code className="text-primary font-mono">float64</code>, <code className="text-primary font-mono">string</code>) define memory storage format. Semantic roles (<code className="text-primary font-mono">IDENTIFIER</code>, <code className="text-primary font-mono">DIMENSION</code>, <code className="text-primary font-mono">MEASURE</code>, <code className="text-primary font-mono">DATETIME</code>) define analytical purpose. Overriding a semantic role makes it authoritative for downstream queries without altering physical storage.
                </p>
              </div>
            </div>

            {/* Semantic Roles Columns Table */}
            <div className="border border-border rounded-lg overflow-hidden bg-surface">
              <table className="w-full text-xs text-left">
                <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                  <tr>
                    <th className="p-3 font-semibold">Column Name</th>
                    <th className="p-3 font-semibold">Physical Datatype</th>
                    <th className="p-3 font-semibold">System Inferred Role</th>
                    <th className="p-3 font-semibold">Authoritative Role Override</th>
                    <th className="p-3 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {availableColumns.map((colName) => {
                    const colMeta = Array.isArray(metadata?.columns)
                      ? metadata.columns.find(
                          (s: any) => (typeof s === 'object' && (s.original_name === colName || s.name === colName))
                        )
                      : null;
                    const dtype = metadata?.dtypes?.[colName] || (colMeta && typeof colMeta === 'object' ? (colMeta as any).detected_datatype : 'string') || 'string';
                    const semRole = (colMeta && typeof colMeta === 'object' ? (colMeta as any).semantic_role : 'UNKNOWN') || 'UNKNOWN';
                    const currentOverride = userRoleOverrides[colName] || semRole;
                    const isSelected = selectedRoleCol === colName;

                    return (
                      <tr
                        key={colName}
                        className={`hover:bg-surface-muted/30 transition-colors ${
                          isSelected ? 'bg-primary/5' : ''
                        }`}
                      >
                        <td className="p-3 font-mono font-bold text-foreground">
                          {colName}
                        </td>
                        <td className="p-3">
                          <Badge variant="slate" size="xs">
                            {dtype}
                          </Badge>
                        </td>
                        <td className="p-3">
                          <Badge variant="blue" size="xs">
                            {semRole}
                          </Badge>
                        </td>
                        <td className="p-3">
                          <select
                            value={currentOverride}
                            onChange={(e) => {
                              const newRole = e.target.value;
                              setSelectedRoleCol(colName);
                              setSelectedRoleValue(newRole);
                              handlePreviewSemanticRoleOverride(colName, newRole);
                            }}
                            className="text-xs bg-surface border border-border rounded px-2 py-1 text-foreground focus:outline-none focus:border-primary cursor-pointer font-medium"
                          >
                            <option value="IDENTIFIER">IDENTIFIER</option>
                            <option value="DIMENSION">DIMENSION</option>
                            <option value="MEASURE">MEASURE</option>
                            <option value="DATETIME">DATETIME</option>
                            <option value="UNKNOWN">UNKNOWN</option>
                          </select>
                        </td>
                        <td className="p-3 text-right">
                          <Button
                            variant="secondary"
                            size="xs"
                            onClick={() => {
                              setSelectedRoleCol(colName);
                              setSelectedRoleValue(currentOverride);
                              handlePreviewSemanticRoleOverride(colName, currentOverride);
                            }}
                            className="text-2xs"
                          >
                            Preview
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Semantic Override Preview Result */}
            {rolePreviewResult && (
              <div className="p-4 bg-surface-muted/30 border border-primary/30 rounded-lg space-y-3 animate-in fade-in duration-150">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-foreground">
                      Semantic Role Override Preview
                    </span>
                    <Badge variant="purple" size="xs">
                      {rolePreviewResult.column_name}
                    </Badge>
                  </div>
                  <button
                    onClick={() => setRolePreviewResult(null)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-2.5 bg-surface border border-border rounded-md text-center">
                    <span className="text-2xs text-muted-foreground block">Physical Type (Preserved)</span>
                    <span className="font-mono font-bold text-foreground text-xs">
                      {rolePreviewResult.physical_dtype}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md text-center">
                    <span className="text-2xs text-muted-foreground block">System Inferred Role</span>
                    <span className="font-bold text-muted-foreground text-xs line-through">
                      {rolePreviewResult.system_role}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface border border-border rounded-md text-center">
                    <span className="text-2xs text-muted-foreground block">User Authoritative Role</span>
                    <span className="font-bold text-primary text-xs">
                      {rolePreviewResult.selected_role}
                    </span>
                  </div>
                </div>

                {rolePreviewResult.evidence && rolePreviewResult.evidence.length > 0 && (
                  <div className="space-y-1 bg-surface-muted/40 p-2.5 rounded border border-border/60 text-2xs text-muted-foreground">
                    {rolePreviewResult.evidence.map((ev, idx) => (
                      <div key={idx} className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                        <span>{ev}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Confirmation Apply Button */}
                <div className="flex items-center justify-between pt-3 border-t border-border/60">
                  <span className="text-2xs text-muted-foreground">
                    Authoritative override will persist for all subsequent analytical modules.
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="xs"
                      onClick={() => setRolePreviewResult(null)}
                    >
                      Dismiss
                    </Button>
                    <Button
                      variant="primary"
                      size="xs"
                      onClick={() => handleApplySemanticRoleOverride(rolePreviewResult.column_name, rolePreviewResult.selected_role)}
                      disabled={roleApplyLoading}
                      leftIcon={<Check className="w-3.5 h-3.5" />}
                      className="text-xs"
                    >
                      {roleApplyLoading ? 'Applying...' : 'Apply Authoritative Role Override'}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* 3. Filter & Selection Management Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-2 border-b border-border">
        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setActiveFilter('ALL')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'ALL'
                ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            All ({cleaningPlan.total_recommendations})
          </button>

          <button
            onClick={() => setActiveFilter('RECOMMENDED')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'RECOMMENDED'
                ? 'bg-emerald-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Recommended ({cleaningPlan.recommended_count})
          </button>

          <button
            onClick={() => setActiveFilter('REVIEW_REQUIRED')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeFilter === 'REVIEW_REQUIRED'
                ? 'bg-amber-600 text-white font-semibold shadow-2xs'
                : 'bg-surface-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Requires Decision ({cleaningPlan.review_required_count})
          </button>

          <button
            onClick={() => setActiveFilter('SELECTED')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
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
            className="text-xs bg-surface border border-border rounded-md px-3 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary w-48"
          />

          <Button
            variant="ghost"
            size="xs"
            onClick={selectAllSafe}
            className="text-xs"
          >
            Select All Safe
          </Button>

          <Button
            variant="ghost"
            size="xs"
            onClick={deselectAll}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Deselect All
          </Button>
        </div>
      </div>

      {/* 3. Recommendation List */}
      <div className="space-y-4">
        {filteredRecommendations.map((rec) => {
          const isSelected = !!selections[rec.recommendation_id];
          const currentOp = methodOverrides[rec.recommendation_id] || rec.user_selected_operation || rec.operation;
          const customVal = customValues[rec.recommendation_id] ?? '';
          const isModified = currentOp !== rec.operation || customVal.trim() !== '';
          const isDiagnostic = isDiagnosticOnly(rec.operation);
          const isReviewRequired = rec.requires_review && !isDiagnostic;
          const isSpecificValue = currentOp === 'IMPUTE_SPECIFIC_VALUE' || currentOp === 'FILL_SPECIFIC_VALUE';

          const riskBadgeVariant: 'green' | 'amber' | 'red' =
            rec.risk_level === 'LOW'
              ? 'green'
              : rec.risk_level === 'MEDIUM'
              ? 'amber'
              : 'red';

          const riskLabel =
            rec.risk_level === 'LOW'
              ? 'Low Risk'
              : rec.risk_level === 'MEDIUM'
              ? 'Medium Risk'
              : 'High Risk';

          const originalVariantLabel =
            rec.supported_variants?.find((v) => v.operation === rec.operation)?.label ||
            rec.operation.replace(/_/g, ' ');

          const currentChoiceLabel =
            rec.supported_variants?.find((v) => v.operation === currentOp)?.label ||
            currentOp.replace(/_/g, ' ');

          // Friendly Category / Problem Name
          const problemTitle = rec.category.replace(/_/g, ' ');

          return (
            <Card
              key={rec.recommendation_id}
              className={`p-5 border transition-all ${
                isSelected
                  ? 'border-primary/50 bg-primary-soft/10 shadow-xs'
                  : 'border-border bg-surface opacity-90 hover:opacity-100'
              }`}
            >
              <div className="space-y-4">
                {/* 1. Header: Target Scope, Risk Badge, and Status */}
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => toggleSelection(rec.recommendation_id)}
                      className="mt-1 text-primary hover:text-primary-hover focus:outline-none"
                      title={isSelected ? 'Deselect from plan' : 'Select for plan'}
                    >
                      {isSelected ? (
                        <CheckSquare className="w-5 h-5 text-primary" />
                      ) : (
                        <Square className="w-5 h-5 text-muted-foreground hover:text-foreground" />
                      )}
                    </button>

                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        {rec.column_name ? (
                          <span className="text-base font-bold text-foreground">
                            {rec.column_name}
                          </span>
                        ) : (
                          <span className="text-base font-bold text-foreground">
                            Whole Dataset
                          </span>
                        )}

                        <Badge variant={riskBadgeVariant} size="xs">
                          {riskLabel}
                        </Badge>

                        {isDiagnostic ? (
                          <Badge variant="amber" size="xs">
                            Review Only
                          </Badge>
                        ) : isReviewRequired ? (
                          <Badge variant="amber" size="xs">
                            Requires your decision
                          </Badge>
                        ) : (
                          <Badge variant="green" size="xs">
                            Recommended
                          </Badge>
                        )}

                        {isModified && (
                          <Badge variant="blue" size="xs">
                            Modified
                          </Badge>
                        )}
                      </div>

                      {/* Problem and Scope count */}
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">{problemTitle}</span>
                        <span>·</span>
                        <span>
                          <strong className="text-foreground">{rec.affected_rows.toLocaleString()} values</strong> ({rec.affected_percentage}% of rows)
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Right side quick toggle button */}
                  <button
                    onClick={() => toggleSelection(rec.recommendation_id)}
                    className={`px-3 py-1 rounded-md text-xs font-medium border transition-colors ${
                      isSelected
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-surface-muted text-muted-foreground hover:text-foreground border-border'
                    }`}
                  >
                    {isSelected ? 'Selected' : 'Include'}
                  </button>
                </div>

                {/* 2. State Guidance / Diagnostic Banner */}
                {isDiagnostic && (
                  <div
                    className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg text-xs border ${
                      isSelected
                        ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400'
                        : 'bg-surface-muted/70 border-border text-muted-foreground'
                    }`}
                  >
                    <Info className="w-4 h-4 shrink-0" />
                    <span>
                      {isSelected
                        ? 'Selected for review. No automatic transformation will be applied.'
                        : 'Review only. Select to include in cleaning report summary.'}
                    </span>
                  </div>
                )}

                {/* 3. Recommended Action & User Choice Controls */}
                {!isDiagnostic && rec.supported_variants && rec.supported_variants.length > 0 && (
                  <div className="p-3.5 bg-surface-muted/30 border border-border/80 rounded-lg space-y-3">
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-foreground">
                          {isReviewRequired ? 'Choose Action:' : 'Action:'}
                        </span>
                        {isModified && (
                          <span className="text-2xs text-muted-foreground">
                            System recommended: <strong className="text-foreground">{originalVariantLabel}</strong>
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        <select
                          value={currentOp}
                          onChange={(e) => {
                            const val = e.target.value;
                            setMethodOverrides((prev) => ({
                              ...prev,
                              [rec.recommendation_id]: val,
                            }));
                          }}
                          className="text-xs bg-surface border border-border rounded-md px-3 py-1.5 text-foreground focus:outline-none focus:border-primary cursor-pointer min-w-[200px]"
                        >
                          {rec.supported_variants.map((v) => (
                            <option key={v.operation} value={v.operation}>
                              {v.label}
                            </option>
                          ))}
                        </select>

                        {!isModified && (
                          <span className="text-2xs text-muted-foreground">
                            (Default recommendation)
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Specific Value Custom Input */}
                    {isSpecificValue && (
                      <div className="pt-2 border-t border-border/60 flex items-center gap-3 flex-wrap">
                        <span className="text-xs font-semibold text-primary">
                          Fill value:
                        </span>
                        <input
                          type={currentOp === 'IMPUTE_SPECIFIC_VALUE' ? 'number' : 'text'}
                          step="any"
                          value={customVal}
                          onChange={(e) => {
                            const val = e.target.value;
                            setCustomValues((prev) => ({
                              ...prev,
                              [rec.recommendation_id]: val,
                            }));
                          }}
                          placeholder={currentOp === 'IMPUTE_SPECIFIC_VALUE' ? 'e.g. 15.0' : 'e.g. Unknown'}
                          className="text-xs bg-surface border border-primary/40 focus:border-primary rounded-md px-3 py-1.5 text-foreground w-48"
                        />
                        <span className="text-2xs text-muted-foreground">
                          {currentOp === 'IMPUTE_SPECIFIC_VALUE'
                            ? 'Enter custom numeric constant'
                            : 'Enter custom text constant'}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* 4. Why & Expected Result in 2 Columns */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-border/60 text-xs">
                  <div className="space-y-1">
                    <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider block">
                      Why this is recommended
                    </span>
                    <p className="text-foreground leading-relaxed">
                      {rec.rationale}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider block">
                      Expected result
                    </span>
                    <p className="text-foreground leading-relaxed">
                      {rec.expected_effect}
                    </p>
                  </div>
                </div>

                {/* 5. Evidence Section */}
                {rec.evidence && rec.evidence.length > 0 && (
                  <div className="pt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider mr-1">
                      Evidence:
                    </span>
                    {rec.evidence.map((evStr, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-0.5 bg-surface-muted border border-border rounded-md text-2xs text-muted-foreground"
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
          <Card className="p-10 text-center space-y-2">
            <div className="w-10 h-10 rounded-full bg-surface-muted flex items-center justify-center mx-auto text-muted-foreground">
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            </div>
            <h4 className="text-sm font-bold text-foreground">No Recommendations Found</h4>
            <p className="text-xs text-muted-foreground">
              No cleaning recommendations match the current filter or search criteria.
            </p>
          </Card>
        )}
      </div>

      {/* 4. Action Bar (Preview & Batch Apply) */}
      <Card className="p-4 border border-primary/30 bg-primary-soft/10 flex flex-col sm:flex-row items-center justify-between gap-4 sticky bottom-4 shadow-lg backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg text-primary shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-bold text-foreground">
                Cleaning Plan Execution
              </h4>
              <Badge variant={(selectedCount + customTransformations.length) > 0 ? 'blue' : 'slate'} size="xs">
                {selectedCount} Plan Ops {customTransformations.length > 0 ? `+ ${customTransformations.length} Manual` : ''}
                {modifiedCount > 0 ? ` · ${modifiedCount} Modified` : ''}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Review simulated changes before applying. Cleaned DataFrame is stored separately in-memory.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGeneratePreview}
            disabled={(selectedCount + customTransformations.length) === 0 || isLoadingPreview || executionState === 'applying' || executionState === 'validating'}
            leftIcon={<Eye className="w-3.5 h-3.5" />}
            className="text-xs"
          >
            {isLoadingPreview ? 'Simulating...' : 'Preview Changes'}
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleApplyCleaning}
            disabled={(selectedCount + customTransformations.length) === 0 || executionState === 'applying' || executionState === 'validating'}
            leftIcon={<Play className="w-3.5 h-3.5" />}
            className="text-xs"
          >
            Apply Cleaning ({selectedCount + customTransformations.length})
          </Button>
        </div>
      </Card>

      {/* 5. Preview Modal / Slide-Over */}
      {isPreviewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-border flex items-center justify-between bg-surface-muted/30">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-primary/10 text-primary">
                  <Eye className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    Cleaning Operations Preview
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Deterministic simulation across {selectedCount + customTransformations.length} selected and manual operations. Raw data is untouched.
                  </p>
                </div>
              </div>

              <button
                onClick={() => setIsPreviewOpen(false)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-5 flex-1 text-xs">
              {previewError && (
                <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-500 text-xs">
                  {previewError}
                </div>
              )}

              {previewResult && (
                <>
                  {/* Summary Comparison Grid */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-2xs text-muted-foreground block font-medium">
                        Rows Before
                      </span>
                      <div className="text-sm font-bold text-foreground">
                        {previewResult.original_row_count.toLocaleString()}
                      </div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-2xs text-muted-foreground block font-medium">
                        Rows After Preview
                      </span>
                      <div className="text-sm font-bold text-emerald-500">
                        {previewResult.preview_row_count.toLocaleString()}
                      </div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-lg space-y-1">
                      <span className="text-2xs text-muted-foreground block font-medium">
                        Net Row Change
                      </span>
                      <div className="text-sm font-bold text-foreground">
                        {previewResult.row_count_change === 0
                          ? '0'
                          : `${previewResult.row_count_change.toLocaleString()} rows`}
                      </div>
                    </div>
                  </div>

                  {/* Operations Summary */}
                  <div className="space-y-2.5">
                    <span className="text-xs font-bold text-foreground block">
                      Transformation Comparison ({previewResult.operations.length} operations)
                    </span>
                    <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                      {previewResult.operations.map((op, i) => (
                        <div
                          key={i}
                          className="p-3 bg-surface border border-border/80 rounded-lg space-y-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              {op.column_name ? (
                                <span className="font-semibold text-foreground px-2 py-0.5 bg-surface-muted rounded text-xs border border-border">
                                  {op.column_name}
                                </span>
                              ) : (
                                <Badge variant="blue" size="xs">
                                  DATASET-WIDE
                                </Badge>
                              )}
                              <span className="font-semibold text-foreground text-xs">
                                {op.operation.replace(/_/g, ' ')}
                              </span>
                            </div>

                            <Badge
                              variant={
                                op.status === 'APPLIED'
                                  ? 'green'
                                  : op.status === 'REVIEW_ONLY'
                                  ? 'amber'
                                  : op.status === 'WARNING'
                                  ? 'amber'
                                  : 'slate'
                              }
                              size="xs"
                            >
                              {op.status === 'REVIEW_ONLY' ? 'Review Only' : op.status}
                            </Badge>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1 border-t border-border/60 text-2xs">
                            <div>
                              <span className="text-muted-foreground block">Before:</span>
                              <span className={op.status === 'REVIEW_ONLY' ? 'text-muted-foreground font-semibold' : 'text-rose-500 font-semibold'}>
                                {op.before_statistic}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground block">After:</span>
                              <span className={op.status === 'REVIEW_ONLY' ? 'text-blue-500 dark:text-blue-400 font-semibold' : 'text-emerald-500 font-semibold'}>
                                {op.after_statistic}
                              </span>
                            </div>
                            <div className="col-span-2 sm:col-span-1">
                              <span className="text-muted-foreground block">Method:</span>
                              <span className="text-foreground truncate block">{op.method_used}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Sample Changed Cells Table */}
                  {previewResult.sample_changes.length > 0 && (
                    <div className="space-y-2 pt-2 border-t border-border">
                      <span className="text-xs font-bold text-foreground block">
                        Sample Cell Modifications (First {previewResult.sample_changes.length} changed items)
                      </span>
                      <div className="border border-border rounded-lg overflow-hidden max-h-40 overflow-y-auto">
                        <table className="w-full text-2xs text-left">
                          <thead className="bg-surface-muted text-muted-foreground border-b border-border">
                            <tr>
                              <th className="p-2">Row</th>
                              <th className="p-2">Column</th>
                              <th className="p-2">Before Value</th>
                              <th className="p-2">Cleaned Value</th>
                              <th className="p-2">Operation</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border font-mono">
                            {previewResult.sample_changes.map((sample, idx) => (
                              <tr key={idx} className="hover:bg-surface-muted/30">
                                <td className="p-2 font-semibold text-muted-foreground">#{sample.row_index}</td>
                                <td className="p-2 font-semibold text-foreground">{sample.column_name}</td>
                                <td className="p-2 text-rose-500 line-through truncate max-w-[120px]">
                                  {sample.before_value === null ? 'NULL' : String(sample.before_value)}
                                </td>
                                <td className="p-2 text-emerald-500 font-bold truncate max-w-[120px]">
                                  {sample.after_value === null ? 'NULL' : String(sample.after_value)}
                                </td>
                                <td className="p-2 text-muted-foreground truncate max-w-[100px] font-sans">{sample.operation}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-border flex items-center justify-between bg-surface-muted/30">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsPreviewOpen(false)}
                className="text-xs"
              >
                Close Preview
              </Button>

              <Button
                variant="primary"
                size="sm"
                onClick={handleApplyCleaning}
                leftIcon={<Play className="w-3.5 h-3.5" />}
                className="text-xs"
              >
                Apply Cleaning Now
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

