import { useState, useEffect } from 'react';
import { getSalaryData } from '../api/marketApi';
import { useApiData } from '../hooks/useApiData';
import PageContainer from '../components/PageContainer';
import Chart from '../components/Chart';
import Filters from '../components/Filters';
import MetricCard from '../components/MetricCard';
import ForecastPanel from '../components/ForecastPanel';
import { CircularProgress, Alert, Box, Typography, Paper, Grid, Stack } from '@mui/material';
import { motion } from 'framer-motion';

const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1, transition: { duration: 0.5 } },
};

const formatCurrency = (value) => (typeof value === 'number' ? `$${Math.round(value).toLocaleString()}` : '—');

const SalaryPage = () => {
    const [filters, setFilters] = useState({ category: null, experience_min: 0, forecast_days: 365, model: 'prophet' });
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
            </Stack>

            <Filters filters={filters} onFilterChange={handleFilterChange} />

            {loading && !data && <CircularProgress sx={{ display: 'block', margin: 'auto' }} />}
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
                        <MetricCard label="Top quartile median" value={formatCurrency(data.summary.top_quartile_median)} delay={0.16} />
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

                    {data?.salary_distribution ? (
                        <>
                            <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                                <Paper className="glass-paper" sx={{ p: 2.2, minHeight: 460 }}>
                                    <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                        Зарплата vs Досвід
                                    </Typography>
                                    {data.salary_distribution.by_experience?.length ? (
                                        <Box sx={{ height: 390 }}>
                                            <Chart
                                                data={[
                                                    {
                                                        x: data.salary_distribution.by_experience.map((d) => d.experience),
                                                        y: data.salary_distribution.by_experience.map((d) => d.avg_salary),
                                                        type: 'bar',
                                                        marker: { color: '#90caf9' },
                                                    },
                                                ]}
                                                layout={{ title: 'Медіанна зарплата ($)', xaxis: { title: 'Роки досвіду' }, autosize: true }}
                                            />
                                        </Box>
                                    ) : (
                                        <Alert severity="info">Немає даних про зарплати в цьому зрізі (джерела без ЗП). Увімкни Adzuna/LinkedIn для salary-аналітики.</Alert>
                                    )}
                                </Paper>
                            </Grid>

                            <Grid item xs={12} component={motion.div} variants={itemVariants} initial="hidden" animate="visible">
                                <Paper className="glass-paper" sx={{ p: 2.2, minHeight: 460 }}>
                                    <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                        Розподіл по квартилях
                                    </Typography>
                                    {data.salary_distribution.by_quartile?.length ? (
                                        <Box sx={{ height: 390 }}>
                                            <Chart
                                                data={[
                                                    {
                                                        x: data.salary_distribution.by_quartile.map((d) => d.salary_quartile),
                                                        y: data.salary_distribution.by_quartile.map((d) => d.median),
                                                        type: 'bar',
                                                        marker: { color: ['#4f5a84', '#7a85b4', '#90caf9', '#d9eeff'] },
                                                    },
                                                ]}
                                                layout={{ title: 'Медіанна зарплата ($)', yaxis: { title: 'Зарплата ($)' }, autosize: true }}
                                            />
                                        </Box>
                                    ) : (
                                        <Alert severity="info">Немає salary-даних для квартилів у цьому зрізі. Увімкни Adzuna/LinkedIn (вони мають зарплати).</Alert>
                                    )}
                                </Paper>
                            </Grid>
                        </>
                    ) : null}
                </Grid>
            ) : null}
        </PageContainer>
    );
};

export default SalaryPage;
