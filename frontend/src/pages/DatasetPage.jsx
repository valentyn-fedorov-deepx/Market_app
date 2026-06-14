import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    Alert,
    Autocomplete,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    IconButton,
    MenuItem,
    Paper,
    Snackbar,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from '@mui/material';
import { DataGrid, GridActionsCellItem } from '@mui/x-data-grid';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import EditRoundedIcon from '@mui/icons-material/EditRounded';
import DeleteRoundedIcon from '@mui/icons-material/DeleteRounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import FileDownloadRoundedIcon from '@mui/icons-material/FileDownloadRounded';
import { motion } from 'framer-motion';
import PageContainer from '../components/PageContainer';
import {
    createDatasetRecord,
    deleteDatasetRecord,
    getDataset,
    getDatasetSources,
    getFilterOptions,
    updateDatasetRecord,
} from '../api/marketApi';

const EMPTY_FORM = {
    title: '',
    company_name: '',
    category_name: '',
    experience: 0,
    public_salary_min: '',
    public_salary_max: '',
    skills: [],
    domain: '',
    published: '',
    long_description: '',
};

const INLINE_EDITABLE = ['title', 'company_name', 'category_name', 'experience', 'public_salary_min', 'public_salary_max', 'domain'];

const toNumberOrNull = (value) => {
    if (value === '' || value === null || value === undefined) return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
};

const DatasetPage = () => {
    const [rows, setRows] = useState([]);
    const [rowCount, setRowCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
    const [sortModel, setSortModel] = useState([{ field: 'published', sort: 'desc' }]);

    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [categoryFilter, setCategoryFilter] = useState(null);
    const [sourceFilter, setSourceFilter] = useState('');

    const [categories, setCategories] = useState([]);
    const [skillOptions, setSkillOptions] = useState([]);
    const [sources, setSources] = useState([]);

    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogMode, setDialogMode] = useState('add');
    const [form, setForm] = useState(EMPTY_FORM);
    const [editingId, setEditingId] = useState(null);
    const [saving, setSaving] = useState(false);

    const [confirmDeleteId, setConfirmDeleteId] = useState(null);
    const [toast, setToast] = useState(null);

    // Debounce the free-text search box.
    useEffect(() => {
        const handle = setTimeout(() => setSearch(searchInput), 400);
        return () => clearTimeout(handle);
    }, [searchInput]);

    // Reset to the first page whenever a filter changes.
    useEffect(() => {
        setPaginationModel((prev) => ({ ...prev, page: 0 }));
    }, [search, categoryFilter, sourceFilter]);

    const loadOptions = useCallback(async () => {
        try {
            const [options, sourceData] = await Promise.all([getFilterOptions({}), getDatasetSources()]);
            setCategories(options.categories || []);
            setSkillOptions(options.skills || []);
            setSources(sourceData.sources || []);
        } catch (err) {
            console.error('Failed to load dataset options', err);
        }
    }, []);

    const loadData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const sort = sortModel[0];
            const data = await getDataset({
                q: search || undefined,
                category: categoryFilter || undefined,
                source: sourceFilter || undefined,
                sort_by: sort?.field || 'published',
                sort_dir: sort?.sort || 'desc',
                page: paginationModel.page + 1,
                page_size: paginationModel.pageSize,
            });
            setRows(data.items || []);
            setRowCount(data.total || 0);
        } catch (err) {
            setError(err?.response?.data?.detail || err.message);
        } finally {
            setLoading(false);
        }
    }, [search, categoryFilter, sourceFilter, sortModel, paginationModel]);

    useEffect(() => {
        loadOptions();
    }, [loadOptions]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const openAddDialog = () => {
        setDialogMode('add');
        setForm(EMPTY_FORM);
        setEditingId(null);
        setDialogOpen(true);
    };

    const openEditDialog = (row) => {
        setDialogMode('edit');
        setEditingId(row.id);
        setForm({
            title: row.title || '',
            company_name: row.company_name || '',
            category_name: row.category_name || '',
            experience: row.experience ?? 0,
            public_salary_min: row.public_salary_min ?? '',
            public_salary_max: row.public_salary_max ?? '',
            skills: row.skills || [],
            domain: row.domain || '',
            published: row.published ? row.published.slice(0, 10) : '',
            long_description: row.long_description || '',
        });
        setDialogOpen(true);
    };

    const handleFormChange = (field) => (event) => {
        setForm((prev) => ({ ...prev, [field]: event.target.value }));
    };

    const buildPayload = () => ({
        title: form.title.trim(),
        company_name: form.company_name.trim() || 'Unknown',
        category_name: form.category_name?.trim() || 'Other',
        experience: Number(form.experience) || 0,
        public_salary_min: toNumberOrNull(form.public_salary_min),
        public_salary_max: toNumberOrNull(form.public_salary_max),
        skills: form.skills || [],
        domain: form.domain?.trim() || null,
        published: form.published ? new Date(form.published).toISOString() : null,
        long_description: form.long_description?.trim() || null,
    });

    const handleSave = async () => {
        if (!form.title.trim()) {
            setToast({ severity: 'warning', message: 'Вкажи назву вакансії (title).' });
            return;
        }
        setSaving(true);
        try {
            const payload = buildPayload();
            if (dialogMode === 'add') {
                await createDatasetRecord(payload);
                setToast({ severity: 'success', message: 'Запис додано.' });
            } else {
                await updateDatasetRecord(editingId, payload);
                setToast({ severity: 'success', message: 'Запис оновлено.' });
            }
            setDialogOpen(false);
            await loadData();
            loadOptions();
        } catch (err) {
            setToast({ severity: 'error', message: err?.response?.data?.detail || err.message });
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        const id = confirmDeleteId;
        setConfirmDeleteId(null);
        try {
            await deleteDatasetRecord(id);
            setToast({ severity: 'success', message: 'Запис видалено.' });
            await loadData();
        } catch (err) {
            setToast({ severity: 'error', message: err?.response?.data?.detail || err.message });
        }
    };

    // Inline cell edit -> PUT only the changed editable fields.
    const processRowUpdate = async (newRow, oldRow) => {
        const changed = {};
        INLINE_EDITABLE.forEach((field) => {
            if (newRow[field] !== oldRow[field]) {
                if (field === 'experience') changed[field] = Number(newRow[field]) || 0;
                else if (field === 'public_salary_min' || field === 'public_salary_max') changed[field] = toNumberOrNull(newRow[field]);
                else changed[field] = newRow[field];
            }
        });
        if (Object.keys(changed).length === 0) return oldRow;
        const updated = await updateDatasetRecord(newRow.id, changed);
        setToast({ severity: 'success', message: 'Поле оновлено.' });
        loadOptions();
        return { ...newRow, ...updated };
    };

    const exportCurrentPageCsv = () => {
        if (!rows.length) return;
        const headers = ['id', 'title', 'company_name', 'category_name', 'experience', 'public_salary_min', 'public_salary_max', 'avg_salary', 'skills', 'source', 'published', 'domain'];
        const escape = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
        const lines = [headers.join(',')];
        rows.forEach((row) => {
            lines.push(headers.map((h) => escape(h === 'skills' ? (row.skills || []).join('; ') : row[h])).join(','));
        });
        const blob = new Blob([`﻿${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `dataset_page_${paginationModel.page + 1}.csv`;
        link.click();
        URL.revokeObjectURL(url);
    };

    const columns = useMemo(
        () => [
            { field: 'id', headerName: 'ID', width: 70 },
            { field: 'title', headerName: 'Назва', flex: 2, minWidth: 220, editable: true },
            { field: 'company_name', headerName: 'Компанія', flex: 1, minWidth: 150, editable: true },
            { field: 'category_name', headerName: 'Категорія', flex: 1, minWidth: 150, editable: true },
            { field: 'experience', headerName: 'Досвід', type: 'number', width: 90, editable: true },
            { field: 'public_salary_min', headerName: 'ЗП min', type: 'number', width: 100, editable: true },
            { field: 'public_salary_max', headerName: 'ЗП max', type: 'number', width: 100, editable: true },
            {
                field: 'avg_salary',
                headerName: 'ЗП avg',
                type: 'number',
                width: 100,
                valueFormatter: (value) => (value == null ? '—' : Math.round(value)),
            },
            {
                field: 'skills',
                headerName: 'Навички',
                flex: 1.5,
                minWidth: 200,
                sortable: false,
                renderCell: (params) => (
                    <Stack direction="row" spacing={0.5} sx={{ gap: 0.5, alignItems: 'center', height: '100%', overflow: 'hidden' }}>
                        {(params.value || []).slice(0, 3).map((skill) => (
                            <Chip key={skill} label={skill} size="small" />
                        ))}
                        {(params.value || []).length > 3 ? <Chip label={`+${params.value.length - 3}`} size="small" variant="outlined" /> : null}
                    </Stack>
                ),
            },
            { field: 'source', headerName: 'Джерело', width: 120 },
            {
                field: 'published',
                headerName: 'Дата',
                width: 110,
                valueFormatter: (value) => (value ? String(value).slice(0, 10) : '—'),
            },
            { field: 'domain', headerName: 'Локація', flex: 1, minWidth: 130, editable: true },
            {
                field: 'actions',
                type: 'actions',
                headerName: 'Дії',
                width: 90,
                getActions: (params) => [
                    <GridActionsCellItem key="edit" icon={<EditRoundedIcon />} label="Редагувати" onClick={() => openEditDialog(params.row)} />,
                    <GridActionsCellItem key="delete" icon={<DeleteRoundedIcon />} label="Видалити" onClick={() => setConfirmDeleteId(params.row.id)} />,
                ],
            },
        ],
        [],
    );

    return (
        <PageContainer>
            <Stack spacing={1} sx={{ mb: 2.5 }}>
                <Typography variant="h4" className="aurora-text">
                    Датасет вакансій
                </Typography>
                <Typography variant="body1" color="text.secondary">
                    Переглядай, шукай, фільтруй та редагуй усі записи. Дані беруться напряму з БД (джерело правди).
                </Typography>
            </Stack>

            <Paper className="glass-paper" sx={{ p: 2.2, mb: 2 }}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} sx={{ flexWrap: 'wrap', gap: 1.5 }}>
                    <TextField
                        label="Пошук (назва / компанія / категорія)"
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        size="small"
                        sx={{ flexGrow: 1, minWidth: 240 }}
                    />
                    <Autocomplete
                        size="small"
                        options={categories}
                        value={categoryFilter}
                        onChange={(e, val) => setCategoryFilter(val)}
                        sx={{ minWidth: 200 }}
                        renderInput={(params) => <TextField {...params} label="Категорія" />}
                    />
                    <TextField
                        select
                        label="Джерело"
                        value={sourceFilter}
                        onChange={(e) => setSourceFilter(e.target.value)}
                        size="small"
                        sx={{ minWidth: 160 }}
                    >
                        <MenuItem value="">Усі</MenuItem>
                        {sources.map((src) => (
                            <MenuItem key={src} value={src}>
                                {src}
                            </MenuItem>
                        ))}
                    </TextField>
                    <Box sx={{ flexGrow: 1 }} />
                    <Tooltip title="Експортувати поточну сторінку у CSV">
                        <span>
                            <IconButton onClick={exportCurrentPageCsv} disabled={!rows.length}>
                                <FileDownloadRoundedIcon />
                            </IconButton>
                        </span>
                    </Tooltip>
                    <Tooltip title="Оновити">
                        <IconButton onClick={loadData}>
                            <RefreshRoundedIcon />
                        </IconButton>
                    </Tooltip>
                    <Button variant="contained" startIcon={<AddRoundedIcon />} onClick={openAddDialog}>
                        Додати
                    </Button>
                </Stack>
            </Paper>

            {error ? (
                <Alert severity="error" sx={{ mb: 2 }}>
                    Помилка: {error}
                </Alert>
            ) : null}

            <Paper className="glass-paper" component={motion.div} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} sx={{ p: 1, height: 640 }}>
                <DataGrid
                    rows={rows}
                    columns={columns}
                    getRowId={(row) => row.id}
                    loading={loading}
                    rowCount={rowCount}
                    paginationMode="server"
                    sortingMode="server"
                    filterMode="server"
                    paginationModel={paginationModel}
                    onPaginationModelChange={setPaginationModel}
                    sortModel={sortModel}
                    onSortModelChange={setSortModel}
                    pageSizeOptions={[10, 25, 50, 100]}
                    processRowUpdate={processRowUpdate}
                    onProcessRowUpdateError={(err) => setToast({ severity: 'error', message: err?.response?.data?.detail || err.message })}
                    disableColumnFilter
                    disableRowSelectionOnClick
                    rowHeight={54}
                    sx={{
                        border: 'none',
                        '& .MuiDataGrid-columnHeaders': { background: 'rgba(255,255,255,0.06)' },
                    }}
                />
            </Paper>

            <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{dialogMode === 'add' ? 'Новий запис' : 'Редагувати запис'}</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField label="Назва *" value={form.title} onChange={handleFormChange('title')} fullWidth />
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                            <TextField label="Компанія" value={form.company_name} onChange={handleFormChange('company_name')} fullWidth />
                            <Autocomplete
                                freeSolo
                                options={categories}
                                value={form.category_name}
                                onChange={(e, val) => setForm((prev) => ({ ...prev, category_name: val || '' }))}
                                onInputChange={(e, val) => setForm((prev) => ({ ...prev, category_name: val || '' }))}
                                fullWidth
                                renderInput={(params) => <TextField {...params} label="Категорія" />}
                            />
                        </Stack>
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                            <TextField label="Досвід (років)" type="number" value={form.experience} onChange={handleFormChange('experience')} fullWidth />
                            <TextField label="Дата публікації" type="date" value={form.published} onChange={handleFormChange('published')} fullWidth InputLabelProps={{ shrink: true }} />
                        </Stack>
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                            <TextField label="ЗП min" type="number" value={form.public_salary_min} onChange={handleFormChange('public_salary_min')} fullWidth />
                            <TextField label="ЗП max" type="number" value={form.public_salary_max} onChange={handleFormChange('public_salary_max')} fullWidth />
                        </Stack>
                        <Autocomplete
                            multiple
                            freeSolo
                            options={skillOptions}
                            value={form.skills}
                            onChange={(e, val) => setForm((prev) => ({ ...prev, skills: val }))}
                            renderInput={(params) => <TextField {...params} label="Навички" placeholder="Додай навичку та Enter" />}
                        />
                        <TextField label="Локація / домен" value={form.domain} onChange={handleFormChange('domain')} fullWidth />
                        <TextField label="Опис" value={form.long_description} onChange={handleFormChange('long_description')} fullWidth multiline minRows={2} />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDialogOpen(false)}>Скасувати</Button>
                    <Button variant="contained" onClick={handleSave} disabled={saving}>
                        {dialogMode === 'add' ? 'Додати' : 'Зберегти'}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={confirmDeleteId != null} onClose={() => setConfirmDeleteId(null)}>
                <DialogTitle>Видалити запис #{confirmDeleteId}?</DialogTitle>
                <DialogActions>
                    <Button onClick={() => setConfirmDeleteId(null)}>Скасувати</Button>
                    <Button color="error" variant="contained" onClick={handleDelete}>
                        Видалити
                    </Button>
                </DialogActions>
            </Dialog>

            <Snackbar open={!!toast} autoHideDuration={3500} onClose={() => setToast(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
                {toast ? (
                    <Alert severity={toast.severity} onClose={() => setToast(null)} variant="filled">
                        {toast.message}
                    </Alert>
                ) : null}
            </Snackbar>
        </PageContainer>
    );
};

export default DatasetPage;
