import { useState, useEffect } from 'react';
import { getSalaryData } from '../api/marketApi';
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

const SalaryPage = () => {
    const [filters, setFilters] = useState({ category: null, experience_min: 0, forecast_days: 365 });
    const { data, loading, error, fetchData } = useApiData(getSalaryData);

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
                    Аналітика зарплат і попиту
                </Typography>
                <Typography variant="body1" color="text.secondary">
                    Аналізуй компенсації по досвіду й квартилях, порівнюй категорії та дивись прогноз попиту.
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
                            label="Top quartile median"
                            value={formatCurrency(data.summary.top_quartile_median)}
                            delay={0.16}
                        />
                    </Grid>
                </Grid>
            ) : null}

            {data && (
                <Grid container spacing={4} direction="column">
                    {data.demand_forecast ? (
                        <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                            <Paper className="glass-paper" sx={{ p: 2.2, minHeight: 500 }}>
                                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                                    <Typography variant="h5" gutterBottom sx={{ textAlign: 'center', mb: 0 }}>
                                        Прогноз попиту
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
                                            name: 'Confidence',
                                            showlegend: false,
                                        },
                                        {
                                            x: data.demand_forecast.dates,
                                            y: data.demand_forecast.confidence_lower,
                                            line: { color: 'transparent' },
                                            name: 'Confidence',
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
                                    layout={{ title: `Прогноз для "${filters.category}"` }}
                                />
                            </Paper>
                        </Grid>
                    ) : null}

                    <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                        <Paper className="glass-paper" sx={{ p: 2.2, height: 460 }}>
                            <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                Зарплата vs Досвід
                            </Typography>
                            <Chart
                                data={[
                                    {
                                        x: data.salary_distribution.by_experience.map((d) => d.experience),
                                        y: data.salary_distribution.by_experience.map((d) => d.avg_salary),
                                        type: 'bar',
                                        marker: { color: '#90caf9' },
                                    },
                                ]}
                                layout={{ title: 'Медіанна зарплата ($)', xaxis: { title: 'Роки досвіду' } }}
                            />
                        </Paper>
                    </Grid>

                    <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                        <Paper className="glass-paper" sx={{ p: 2.2, height: 460 }}>
                            <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                Розподіл по квартилях
                            </Typography>
                            <Chart
                                data={[
                                    {
                                        x: data.salary_distribution.by_quartile.map((d) => d.salary_quartile),
                                        y: data.salary_distribution.by_quartile.map((d) => d.median),
                                        type: 'bar',
                                        marker: { color: ['#4f5a84', '#7a85b4', '#90caf9', '#d9eeff'] },
                                    },
                                ]}
                                layout={{ title: 'Медіанна зарплата ($)', yaxis: { title: 'Зарплата ($)' } }}
                            />
                        </Paper>
                    </Grid>
                </Grid>
            )}
        </PageContainer>
    );
};

export default SalaryPage;
