import { useMemo, useState } from 'react';
import {
    Alert,
    Avatar,
    Box,
    CircularProgress,
    Divider,
    Fab,
    IconButton,
    Paper,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from '@mui/material';
import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import InsightsRoundedIcon from '@mui/icons-material/InsightsRounded';
import SendRoundedIcon from '@mui/icons-material/SendRounded';
import SummarizeRoundedIcon from '@mui/icons-material/SummarizeRounded';
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded';
import { AnimatePresence, motion } from 'framer-motion';
import { chatWithAssistant, createAssistantReport, getAssistantInsights } from '../api/marketApi';

const MotionPaper = motion(Paper);

const createLocalMessage = (role, content) => ({
    id: `${Date.now()}-${Math.random()}`,
    role,
    content,
});

const MascotAssistant = () => {
    const [open, setOpen] = useState(false);
    const [input, setInput] = useState('');
    const [messages, setMessages] = useState([
        createLocalMessage(
            'assistant',
            'Привіт! Я Vyz — твій AI-помічник. Можу дати інсайти, пояснити тренди й згенерувати звіт.',
        ),
    ]);
    const [sessionId, setSessionId] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const canSend = useMemo(() => input.trim().length > 0 && !loading, [input, loading]);

    const pushAssistantMessage = (text) => {
        setMessages((prev) => [...prev, createLocalMessage('assistant', text)]);
    };

    const handleSend = async () => {
        if (!canSend) return;
        const message = input.trim();
        setInput('');
        setError(null);
        setMessages((prev) => [...prev, createLocalMessage('user', message)]);
        setLoading(true);
        try {
            const response = await chatWithAssistant({
                message,
                session_id: sessionId,
            });
            setSessionId(response.session_id);
            pushAssistantMessage(response.message);
        } catch (err) {
            setError(err?.response?.data?.detail || err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleInsights = async () => {
        setError(null);
        setLoading(true);
        try {
            const response = await getAssistantInsights();
            pushAssistantMessage(response.narrative);
        } catch (err) {
            setError(err?.response?.data?.detail || err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleReport = async () => {
        setError(null);
        setLoading(true);
        try {
            const response = await createAssistantReport({ horizon_days: 90 });
            pushAssistantMessage(response.report_markdown);
        } catch (err) {
            setError(err?.response?.data?.detail || err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <Tooltip title="Відкрити AI-помічника Vyz">
                <Fab
                    color="primary"
                    aria-label="assistant"
                    onClick={() => setOpen((prev) => !prev)}
                    sx={{
                        position: 'fixed',
                        bottom: 28,
                        right: 28,
                        zIndex: 1300,
                        boxShadow: '0 8px 30px rgba(144,202,249,0.45)',
                    }}
                >
                    {open ? <CloseRoundedIcon /> : <SmartToyRoundedIcon />}
                </Fab>
            </Tooltip>

            <AnimatePresence>
                {open ? (
                    <MotionPaper
                        className="glass-paper"
                        key="assistant-panel"
                        initial={{ opacity: 0, y: 20, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 15, scale: 0.97 }}
                        transition={{ duration: 0.25 }}
                        elevation={10}
                        sx={{
                            position: 'fixed',
                            bottom: 95,
                            right: 24,
                            width: { xs: 'calc(100vw - 28px)', sm: 390 },
                            height: 560,
                            zIndex: 1300,
                            borderRadius: 4,
                            display: 'flex',
                            flexDirection: 'column',
                            overflow: 'hidden',
                        }}
                    >
                        <Box
                            sx={{
                                p: 1.6,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                background:
                                    'linear-gradient(140deg, rgba(144,202,249,0.35), rgba(186,104,200,0.2))',
                            }}
                        >
                            <Stack direction="row" spacing={1.2} alignItems="center">
                                <Avatar sx={{ bgcolor: 'rgba(0,0,0,0.25)' }}>
                                    <AutoAwesomeRoundedIcon />
                                </Avatar>
                                <Box>
                                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                        Vyz Assistant
                                    </Typography>
                                    <Typography variant="caption" sx={{ opacity: 0.85 }}>
                                        Інсайти • Звіти • Поради
                                    </Typography>
                                </Box>
                            </Stack>
                            <IconButton color="inherit" size="small" onClick={() => setOpen(false)}>
                                <CloseRoundedIcon fontSize="small" />
                            </IconButton>
                        </Box>

                        <Stack
                            direction="row"
                            spacing={1}
                            sx={{ px: 1.2, py: 1, borderBottom: '1px solid', borderColor: 'divider' }}
                        >
                            <Tooltip title="Отримати короткі інсайти">
                                <span>
                                    <IconButton size="small" onClick={handleInsights} disabled={loading}>
                                        <InsightsRoundedIcon fontSize="small" />
                                    </IconButton>
                                </span>
                            </Tooltip>
                            <Tooltip title="Згенерувати markdown-звіт">
                                <span>
                                    <IconButton size="small" onClick={handleReport} disabled={loading}>
                                        <SummarizeRoundedIcon fontSize="small" />
                                    </IconButton>
                                </span>
                            </Tooltip>
                            {loading ? <CircularProgress size={18} sx={{ ml: 0.5 }} /> : null}
                        </Stack>

                        <Box sx={{ p: 1.2, flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 1 }}>
                            {messages.map((item) => (
                                <Paper
                                    key={item.id}
                                    elevation={0}
                                    sx={{
                                        p: 1.1,
                                        borderRadius: 2,
                                        bgcolor: item.role === 'assistant' ? 'rgba(144,202,249,0.1)' : 'rgba(255,255,255,0.08)',
                                        border: '1px solid',
                                        borderColor: item.role === 'assistant' ? 'rgba(144,202,249,0.28)' : 'rgba(255,255,255,0.12)',
                                        whiteSpace: 'pre-wrap',
                                        ml: item.role === 'assistant' ? 0 : '12%',
                                        mr: item.role === 'assistant' ? '12%' : 0,
                                    }}
                                >
                                    <Typography variant="body2">{item.content}</Typography>
                                </Paper>
                            ))}
                        </Box>

                        {error ? (
                            <Box sx={{ px: 1.2, pb: 0.8 }}>
                                <Alert severity="error">{error}</Alert>
                            </Box>
                        ) : null}

                        <Divider />
                        <Box sx={{ p: 1.2, display: 'flex', gap: 1, alignItems: 'center' }}>
                            <TextField
                                value={input}
                                onChange={(event) => setInput(event.target.value)}
                                placeholder="Запитай щось у Vyz..."
                                size="small"
                                fullWidth
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter') {
                                        event.preventDefault();
                                        handleSend();
                                    }
                                }}
                            />
                            <IconButton color="primary" onClick={handleSend} disabled={!canSend}>
                                <SendRoundedIcon />
                            </IconButton>
                        </Box>
                    </MotionPaper>
                ) : null}
            </AnimatePresence>
        </>
    );
};

export default MascotAssistant;
