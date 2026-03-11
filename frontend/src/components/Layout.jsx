import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
    AppBar,
    Box,
    Button,
    Chip,
    CircularProgress,
    Container,
    Link,
    Stack,
    Toolbar,
    Tooltip,
    Typography,
} from '@mui/material';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import PsychologyAltRoundedIcon from '@mui/icons-material/PsychologyAltRounded';
import { getSystemStatus, refreshSystemData } from '../api/marketApi';
import MascotAssistant from './MascotAssistant';

const navButtonStyle = ({ isActive }) => ({
    color: isActive ? '#fff' : 'rgba(255,255,255,0.7)',
    border: '1px solid',
    borderColor: isActive ? 'rgba(255,255,255,0.45)' : 'rgba(255,255,255,0.2)',
    background: isActive ? 'rgba(255,255,255,0.12)' : 'transparent',
    textTransform: 'none',
    borderRadius: 10,
    fontWeight: 600,
    padding: '8px 14px',
});

const Layout = () => {
    const [status, setStatus] = useState(null);
    const [refreshing, setRefreshing] = useState(false);

    const loadStatus = async () => {
        try {
            const response = await getSystemStatus();
            setStatus(response?.data_status || null);
        } catch (error) {
            console.error('Failed to load status', error);
        }
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            const response = await refreshSystemData({ force_csv: false });
            setStatus(response?.data_status || null);
        } catch (error) {
            console.error('Refresh failed', error);
        } finally {
            setRefreshing(false);
        }
    };

    useEffect(() => {
        loadStatus();
    }, []);

    const lastRefreshText = useMemo(() => {
        if (!status?.last_refresh) return 'Дані ще не синхронізовані';
        return `Останнє оновлення: ${new Date(status.last_refresh).toLocaleString()}`;
    }, [status]);

    return (
        <Box>
            <AppBar
                position="sticky"
                elevation={0}
                sx={{
                    background: 'rgba(15, 20, 36, 0.65)',
                    backdropFilter: 'blur(14px)',
                    borderBottom: '1px solid rgba(255,255,255,0.12)',
                }}
            >
                <Toolbar sx={{ py: 1, display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 1.2 }}>
                    <Stack direction="row" alignItems="center" spacing={1.2} sx={{ flexGrow: 1 }}>
                        <PsychologyAltRoundedIcon />
                        <Box>
                            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
                                IT Market Intelligence
                            </Typography>
                            <Typography variant="caption" sx={{ opacity: 0.8 }}>
                                AI-powered analytics & forecasting
                            </Typography>
                        </Box>
                    </Stack>

                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems="center">
                        <Chip
                            size="small"
                            label={`Rows: ${status?.rows_in_memory ?? '—'}`}
                            sx={{ bgcolor: 'rgba(144,202,249,0.2)' }}
                        />
                        <Chip
                            size="small"
                            label={lastRefreshText}
                            sx={{ maxWidth: 260 }}
                        />
                        <Tooltip title="Оновити джерела та кеш даних">
                            <span>
                                <Button
                                    onClick={handleRefresh}
                                    color="inherit"
                                    size="small"
                                    startIcon={refreshing ? <CircularProgress size={14} color="inherit" /> : <RefreshRoundedIcon />}
                                    disabled={refreshing}
                                >
                                    Refresh
                                </Button>
                            </span>
                        </Tooltip>
                    </Stack>
                </Toolbar>
                <Toolbar sx={{ pt: 0, pb: 1.2, justifyContent: 'center', gap: 1, flexWrap: 'wrap' }}>
                    <Button component={NavLink} to="/" style={navButtonStyle}>
                        Попит
                    </Button>
                    <Button component={NavLink} to="/salary" style={navButtonStyle}>
                        Зарплати
                    </Button>
                    <Button component={NavLink} to="/skills" style={navButtonStyle}>
                        Навички
                    </Button>
                </Toolbar>
            </AppBar>

            <Container component="main" maxWidth="xl" sx={{ mt: 3, mb: 8 }}>
                <Outlet />
            </Container>

            <Box sx={{ pb: 4, textAlign: 'center', opacity: 0.75 }}>
                <Typography variant="caption">
                    Data sources:{' '}
                    <Link href="https://remotive.com" target="_blank" rel="noopener noreferrer" color="inherit">
                        Remotive
                    </Link>
                    {', '}
                    <Link href="https://remoteok.com" target="_blank" rel="noopener noreferrer" color="inherit">
                        RemoteOK
                    </Link>
                    {', '}
                    <Link href="https://www.arbeitnow.com" target="_blank" rel="noopener noreferrer" color="inherit">
                        Arbeitnow
                    </Link>
                </Typography>
            </Box>

            <MascotAssistant />
        </Box>
    );
};

export default Layout;
