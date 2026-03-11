import { useState, useEffect } from 'react';
import { getSkillsData } from '../api/marketApi';
import { useApiData } from '../hooks/useApiData';
import PageContainer from '../components/PageContainer';
import Chart from '../components/Chart';
import Filters from '../components/Filters';
import MetricCard from '../components/MetricCard';
import { CircularProgress, Alert, Typography, Paper, Grid, Stack } from '@mui/material';
import { motion } from 'framer-motion';

const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
};

const itemVariants = {
    hidden: { y: 14, opacity: 0 },
    visible: { y: 0, opacity: 1 },
};

const formatCurrency = (value) => (typeof value === 'number' ? `$${Math.round(value).toLocaleString()}` : '—');

const SkillsPage = () => {
    const [filters, setFilters] = useState({ category: null, experience_min: 0, skills: [] });
    const { data, loading, error, fetchData } = useApiData(getSkillsData);

    useEffect(() => {
        if (filters.category) {
            fetchData(filters);
        }
    }, [filters, fetchData]);

    const handleFilterChange = (name, value) => {
        setFilters((prev) => ({ ...prev, [name]: value === '' ? undefined : value }));
    };

    const q4Skills = data?.top_skills_by_quartile?.['Q4 (Top)'] || [];
    const topImportance = data?.skill_importance?.skill_importance_for_salary || [];

    return (
        <PageContainer>
            <Stack spacing={1} sx={{ mb: 2.5 }}>
                <Typography variant="h4" className="aurora-text">
                    Аналіз ключових навичок
                </Typography>
                <Typography variant="body1" color="text.secondary">
                    Дивись, які скіли найбільше впливають на зарплату та які патерни мають top-paid вакансії.
                </Typography>
            </Stack>

            <Filters filters={filters} onFilterChange={handleFilterChange} />

            {loading && <CircularProgress sx={{ display: 'block', margin: 'auto' }} />}
            {error && <Alert severity="error">Помилка: {error.response?.data?.detail || error.message}</Alert>}

            {data?.summary ? (
                <Grid container spacing={2} sx={{ mb: 3 }}>
                    <Grid item xs={12} sm={4}>
                        <MetricCard label="Вакансії у сегменті" value={data.summary.total_vacancies} delay={0.03} />
                    </Grid>
                    <Grid item xs={12} sm={4}>
                        <MetricCard label="Медіанна зарплата" value={formatCurrency(data.summary.median_salary)} delay={0.08} />
                    </Grid>
                    <Grid item xs={12} sm={4}>
                        <MetricCard
                            label="Середній досвід"
                            value={`${(data.summary.average_experience || 0).toFixed(1)} р.`}
                            delay={0.12}
                        />
                    </Grid>
                </Grid>
            ) : null}

            {data && (
                <Grid container spacing={4} component={motion.div} variants={containerVariants} initial="hidden" animate="visible">
                    <Grid item xs={12} md={6} component={motion.div} variants={itemVariants}>
                        <Paper className="glass-paper" sx={{ p: 2.2, height: 520 }}>
                            <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                Вплив навичок на зарплату
                            </Typography>
                            <Chart
                                data={[
                                    {
                                        y: topImportance.map((s) => s.skill),
                                        x: topImportance.map((s) => s.importance),
                                        type: 'bar',
                                        orientation: 'h',
                                        marker: { color: '#90caf9' },
                                    },
                                ]}
                                layout={{ title: 'Feature importance (ML)', yaxis: { autorange: 'reversed' } }}
                            />
                        </Paper>
                    </Grid>
                    <Grid item xs={12} md={6} component={motion.div} variants={itemVariants}>
                        <Paper className="glass-paper" sx={{ p: 2.2, height: 520 }}>
                            <Typography variant="h5" gutterBottom sx={{ textAlign: 'center' }}>
                                Топ навичок для Q4 (Top 25% ЗП)
                            </Typography>
                            <Chart
                                data={[
                                    {
                                        y: q4Skills.map((s) => s.skills || s.skill),
                                        x: q4Skills.map((s) => s.count),
                                        type: 'bar',
                                        orientation: 'h',
                                        marker: { color: '#e3f2fd' },
                                    },
                                ]}
                                layout={{ title: 'Найчастіші згадки', yaxis: { autorange: 'reversed' } }}
                            />
                        </Paper>
                    </Grid>
                </Grid>
            )}
        </PageContainer>
    );
};

export default SkillsPage;
