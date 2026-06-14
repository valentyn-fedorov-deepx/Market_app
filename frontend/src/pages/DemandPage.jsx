import { useState, useEffect } from 'react';
import { getDemandData } from '../api/marketApi';
import { useApiData } from '../hooks/useApiData';
import PageContainer from '../components/PageContainer';
import Chart from '../components/Chart';
import Filters from '../components/Filters';
import MetricCard from '../components/MetricCard';
import ForecastPanel from '../components/ForecastPanel';
import { Alert, Box, Typography, Paper, Grid, Stack } from '@mui/material';
import { motion } from 'framer-motion';

const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1, transition: { duration: 0.5 } },
};

const formatCurrency = (value) => (typeof value === 'number' ? `$${Math.round(value).toLocaleString()}` : '—');

const EXPERIENCE_BANDS = [
    { label: 'Junior (0–1)', min: 0, max: 1 },
    { label: 'Middle (2–4)', min: 2, max: 4 },
    { label: 'Senior (5–7)', min: 5, max: 7 },
    { label: 'Lead (8+)', min: 8, max: Infinity },
];

const toExperienceBands = (distribution) =>
    EXPERIENCE_BANDS.map((band) => ({
        label: band.label,
        count: (distribution || [])
            .filter((d) => d.experience >= band.min && d.experience <= band.max)
            .reduce((sum, d) => sum + (d.count || 0), 0),
    })).filter((band) => band.count > 0);

const DemandPage = () => {
    const [filters, setFilters] = useState({ category: null, experience_min: 0, skills: [], model: 'prophet' });
    const { data, loading, error, fetchData } = useApiData(getDemandData);

    useEffect(() => {
        if (filters.category) {
            fetchData(filters);
        }
    }, [filters, fetchData]);

    const handleFilterChange = (name, value) => {
        setFilters((prev) => ({ ...prev, [name]: value === '' ? undefined : value }));
    };

    return (
        <PageContainer>
            <Stack spacing={1} sx={{ mb: 2.5 }}>
                <Typography variant="h4" className="aurora-text">
                    Аналіз попиту на IT-ринку
                </Typography>
                <Typography variant="body1" color="text.secondary">
                    Досліджуй тренди вакансій, обирай модель прогнозу та дивись, як вона навчається на реальних даних.
                </Typography>
            </Stack>

            <Filters filters={filters} onFilterChange={handleFilterChange} />

            {error && <Alert severity="error" sx={{ mb: 2 }}>Помилка: {error.response?.data?.detail || error.message}</Alert>}

            {data?.summary ? (
                <Grid container spacing={2} sx={{ mb: 3 }}>
                    <Grid item xs={12} sm={6} md={3}>
                        <MetricCard label="Вакансії у сегменті" value={data.summary.total_vacancies} delay={0.03} />
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                        <MetricCard label="Середня зарплата" value={formatCurrency(data.summary.average_salary)} delay={0.08} />
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                        <MetricCard label="Медіанна зарплата" value={formatCurrency(data.summary.median_salary)} delay={0.12} />
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                        <MetricCard
                            label="Середній досвід"
                            value={`${(data.summary.average_experience || 0).toFixed(1)} р.`}
                            delay={0.16}
                        />
                    </Grid>
                </Grid>
            ) : null}

            {filters.category ? (
                <Grid container spacing={4} direction="column">
                    <Grid item xs={12}>
                        <ForecastPanel
                            forecast={data?.demand_forecast}
                            loading={loading}
                            category={filters.category}
                            model={filters.model}
                            onModelChange={(value) => handleFilterChange('model', value)}
                        />
                    </Grid>

                    {data?.experience_distribution && data.experience_distribution.length > 0 && (
                        <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                            <Paper className="glass-paper" sx={{ p: 2.2, minHeight: 450 }}>
                                <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                    Розподіл по рівнях досвіду
                                </Typography>
                                <Box sx={{ height: 380 }}>
                                    <Chart
                                        data={[
                                            {
                                                values: toExperienceBands(data.experience_distribution).map((b) => b.count),
                                                labels: toExperienceBands(data.experience_distribution).map((b) => b.label),
                                                type: 'pie',
                                                hole: 0.5,
                                                textinfo: 'label+percent',
                                                sort: false,
                                                direction: 'clockwise',
                                                marker: { colors: ['#4f5a84', '#7a85b4', '#90caf9', '#d9eeff'] },
                                            },
                                        ]}
                                        layout={{ title: 'Частка вакансій за рівнем (Junior / Middle / Senior / Lead)', autosize: true }}
                                    />
                                </Box>
                            </Paper>
                        </Grid>
                    )}
                </Grid>
            ) : null}
        </PageContainer>
    );
};

export default DemandPage;
