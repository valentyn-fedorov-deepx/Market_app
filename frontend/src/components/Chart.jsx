// src/components/Chart.jsx
import Plot from 'react-plotly.js';
import { useTheme } from '@mui/material/styles';

const Chart = ({ data, layout }) => {
    const theme = useTheme();

    const plotlyLayout = {
        ...layout,
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: theme.palette.text.primary, family: theme.typography.fontFamily },
        xaxis: { ...layout?.xaxis, gridcolor: theme.palette.divider },
        yaxis: { ...layout?.yaxis, gridcolor: theme.palette.divider },
        legend: { bgcolor: 'rgba(0,0,0,0.2)', bordercolor: theme.palette.divider },
        transition: { duration: 500, easing: 'cubic-in-out' },
        // ✅ Додаємо автоматичне визначення розміру
        autosize: true,
    };

    return (
        <Plot
            data={data}
            layout={plotlyLayout}
            useResizeHandler={true}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%', height: '100%' }}
        />
    );
};

export default Chart;