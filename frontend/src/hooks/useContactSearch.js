import { useCallback, useEffect, useState } from 'react';
import {
  recipientService, recipientGroupService, tagService, campaignService,
} from '../services/services';
import { FIELD_DEFS } from '../components/FilterBuilder';

const DISTINCT_FIELD_KEYS = FIELD_DEFS.filter((f) => f.type === 'distinct').map((f) => f.key);
const PAGE_SIZE = 10;

/** Shared dynamic filter-builder search logic — used by both the standalone
 * Contacts page and the campaign Contacts tab, so they stay identical
 * instead of drifting as two separate copies. */
export function useContactSearch({ toast, extraParams } = {}) {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

  const [activeFieldKeys, setActiveFieldKeys] = useState([]);
  const [filterValues, setFilterValues] = useState({});
  const [distinctOptions, setDistinctOptions] = useState({});
  const [distinctLoading, setDistinctLoading] = useState({});

  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [groups, setGroups] = useState([]);
  const [tags, setTags] = useState([]);
  const [campaigns, setCampaigns] = useState([]);

  const buildActiveParams = () => {
    const params = { search, sort_by: sortBy, sort_order: sortOrder, ...(extraParams || {}) };
    activeFieldKeys.forEach((key) => {
      if (key === 'campaign_status') {
        if (filterValues.campaign_id) params.campaign_id = filterValues.campaign_id;
        if (filterValues.campaign_status) params.campaign_status = filterValues.campaign_status;
        return;
      }
      const value = filterValues[key];
      if (Array.isArray(value) && value.length > 0) params[key] = value;
      else if (typeof value === 'string' && value) params[key] = value;
    });
    return params;
  };

  const activeParams = buildActiveParams();

  const loadResults = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await recipientService.search({ page, page_size: PAGE_SIZE, ...activeParams });
      setResults(data.items);
      setTotal(data.total);
    } catch {
      toast?.error('Search failed');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, JSON.stringify(activeParams)]);

  useEffect(() => { loadResults(); }, [loadResults]);

  const loadGroups = useCallback(() => {
    recipientGroupService.getAll().then(({ data }) => setGroups(data)).catch(() => {});
  }, []);
  const loadTags = useCallback(() => {
    tagService.getAll().then(({ data }) => setTags(data)).catch(() => {});
  }, []);

  useEffect(() => {
    loadGroups();
    loadTags();
    campaignService.getAll().then(({ data }) => setCampaigns(data)).catch(() => {});
  }, [loadGroups, loadTags]);

  const fetchDistinctValues = useCallback((key) => {
    setDistinctLoading((p) => ({ ...p, [key]: true }));
    recipientService
      .distinctValues(key)
      .then(({ data }) => setDistinctOptions((p) => ({ ...p, [key]: data.values })))
      .catch(() => {})
      .finally(() => setDistinctLoading((p) => ({ ...p, [key]: false })));
  }, []);

  useEffect(() => {
    activeFieldKeys
      .filter((key) => DISTINCT_FIELD_KEYS.includes(key) && !distinctOptions[key] && !distinctLoading[key])
      .forEach(fetchDistinctValues);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFieldKeys]);

  const refreshActiveDistinctOptions = () => {
    activeFieldKeys.filter((key) => DISTINCT_FIELD_KEYS.includes(key)).forEach(fetchDistinctValues);
  };

  const handleAddField = (key) => {
    setActiveFieldKeys((prev) => [...prev, key]);
    setPage(1);
  };

  const handleRemoveField = (key) => {
    setActiveFieldKeys((prev) => prev.filter((k) => k !== key));
    setFilterValues((prev) => {
      const next = { ...prev };
      delete next[key];
      if (key === 'campaign_status') { delete next.campaign_id; delete next.campaign_status; }
      return next;
    });
    setPage(1);
  };

  const handleValueChange = (key, value) => {
    setFilterValues((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const clearAllFilters = () => {
    setActiveFieldKeys([]);
    setFilterValues({});
    setSearch('');
    setPage(1);
  };

  const loadSavedSearchFilters = (savedFilters) => {
    const f = savedFilters || {};
    const newActive = new Set();
    Object.keys(f).forEach((k) => {
      if (k === 'campaign_id' || k === 'campaign_status') newActive.add('campaign_status');
      else if (FIELD_DEFS.some((d) => d.key === k)) newActive.add(k);
    });
    setActiveFieldKeys([...newActive]);
    setFilterValues(f);
    setSearch(f.search || '');
    setSortBy(f.sort_by || 'name');
    setSortOrder(f.sort_order || 'asc');
    setPage(1);
  };

  return {
    search, setSearch, sortBy, setSortBy, sortOrder, setSortOrder,
    activeFieldKeys, filterValues, distinctOptions, distinctLoading,
    results, total, page, setPage, loading, activeParams,
    groups, tags, campaigns, loadGroups, loadTags,
    handleAddField, handleRemoveField, handleValueChange, clearAllFilters,
    refreshActiveDistinctOptions, loadSavedSearchFilters, loadResults,
  };
}
