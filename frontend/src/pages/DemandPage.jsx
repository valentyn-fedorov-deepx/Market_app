import { useState, useEffect } from 'react';
import { getDemandData } from '../api/marketApi';
import { useApiData } from '../hooks/useApiData';
import PageContainer from '../components/PageContainer';
import Chart from '../components/Chart';
import Filters from '../components/Filters';
import MetricCard from '../components/MetricCard';
import { CircularProgress, Alert, Typography, Paper, Grid, Stack, Chip } from '@mui/material';
import { motion } from 'framer-motion';

const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1, transition: { duration: 0.5 } },
};

const formatCurrency = (value) => (typeof value === 'number' ? `$${Math.round(value).toLocaleString()}` : '—');

const DemandPage = () => {
    const [filters, setFilters] = useState({ category: null, experience_min: 0, skills: [] });
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
                    Досліджуй тренди вакансій, порівнюй сегменти та перевіряй прогнози з адаптивним model selection.
                </Typography>
            </Stack>

            <Filters filters={filters} onFilterChange={handleFilterChange} />

            {loading && <CircularProgress sx={{ display: 'block', margin: 'auto' }} />}
            {error && <Alert severity="error">Помилка: {error.response?.data?.detail || error.message}</Alert>}

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

            {data && (
                <Grid container spacing={4} direction="column">
                    {data.demand_forecast && (
                        <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                            <Paper className="glass-paper" sx={{ p: 2.2, minHeight: 460 }}>
                                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                                    <Typography variant="h5" sx={{ textAlign: 'center' }}>
                                        Прогноз попиту для "{filters.category}"
                                    </Typography>
                                    <Chip
                                        size="small"
                                        label={`Model: ${data.demand_forecast.model_used || 'auto'}`}
                                        sx={{ bgcolor: 'rgba(144,202,249,0.2)' }}
                                    />
                                </Stack>
                                <Chart
                                    data={[
                                        {
                                            x: data.demand_forecast.dates,
                                            y: data.demand_forecast.confidence_upper,
                                            fill: 'tonexty',
                                            fillcolor: 'rgba(144, 202, 249, 0.2)',
                                            line: { color: 'transparent' },
                                            name: 'Довірчий інтервал',
                                            showlegend: false,
                                        },
                                        {
                                            x: data.demand_forecast.dates,
                                            y: data.demand_forecast.confidence_lower,
                                            line: { color: 'transparent' },
                                            name: 'Довірчий інтервал',
                                            showlegend: false,
                                        },
                                        {
                                            x: data.demand_forecast.historical_dates,
                                            y: data.demand_forecast.historical_demand,
                                            mode: 'lines',
                                            name: 'Історія',
                                            line: { color: '#9aa3b4' },
                                        },
                                        {
                                            x: data.demand_forecast.dates,
                                            y: data.demand_forecast.predicted_demand,
                                            mode: 'lines',
                                            name: 'Прогноз',
                                            line: { color: '#90caf9', width: 3 },
                                        },
                                    ]}
                                    layout={{ title: 'Динаміка та прогноз кількості вакансій' }}
                                />
                            </Paper>
                        </Grid>
                    )}

                    {data.experience_distribution && data.experience_distribution.length > 0 && (
                        <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                            <Paper className="glass-paper" sx={{ p: 2.2, minHeight: 450 }}>
                                <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                    Розподіл по досвіду
                                </Typography>
                                <Chart
                                    data={[
                                        {
                                            values: data.experience_distribution.map((d) => d.count),
                                            labels: data.experience_distribution.map((d) => `${d.experience} р.`),
                                            type: 'pie',
                                            hole: 0.45,
                                            textinfo: 'label+percent',
                                            automargin: true,
                                        },
                                    ]}
                                    layout={{ title: 'Частка вакансій у відфільтрованому сегменті', showlegend: false }}
                                />
                            </Paper>
                        </Grid>
                    )}
                </Grid>
            )}
        </PageContainer>
    );
};

export default DemandPage;
