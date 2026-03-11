import { Card, CardContent, Typography, Stack } from '@mui/material';
import { motion } from 'framer-motion';

const MotionCard = motion(Card);

const MetricCard = ({ label, value, helper, delay = 0 }) => (
    <MotionCard
        className="glass-paper"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay }}
        sx={{
            borderRadius: 3,
            minHeight: 120,
            position: 'relative',
            overflow: 'hidden',
            '&::after': {
                content: '""',
                position: 'absolute',
                inset: 0,
                background:
                    'linear-gradient(120deg, rgba(144,202,249,0.15), rgba(206,147,216,0.04), transparent 70%)',
                pointerEvents: 'none',
            },
        }}
    >
        <CardContent>
            <Stack spacing={0.7}>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {label}
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>
                    {value}
                </Typography>
                {helper ? (
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        {helper}
                    </Typography>
                ) : null}
            </Stack>
        </CardContent>
    </MotionCard>
);

export default MetricCard;
