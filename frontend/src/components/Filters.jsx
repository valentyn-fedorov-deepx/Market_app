import { useState, useEffect, useMemo } from 'react';
import {
    Paper,
    TextField,
    Slider,
    Typography,
    Box,
    Autocomplete,
    Checkbox
} from '@mui/material';
import CheckBoxOutlineBlankIcon from '@mui/icons-material/CheckBoxOutlineBlank';
import CheckBoxIcon from '@mui/icons-material/CheckBox';
import { getFilterOptions } from '../api/marketApi';

const icon = <CheckBoxOutlineBlankIcon fontSize="small" />;
const checkedIcon = <CheckBoxIcon fontSize="small" />;

const Filters = ({ filters, onFilterChange }) => {
    const [options, setOptions] = useState({
        categories: [],
        skills: [],
        experienceRange: { min: 0, max: 10 },
        experienceValues: [0],
    });
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const loadOptions = async () => {
            setIsLoading(true);
            try {
                const loadedOptions = await getFilterOptions({
                    category: filters?.category || undefined,
                    experience_min: filters?.experience_min,
                    skills: (filters?.skills || []).length ? filters.skills : undefined,
                });
                setOptions((prev) => ({
                    ...prev,
                    ...loadedOptions,
                    experienceRange: loadedOptions.experience_range || prev.experienceRange,
                    experienceValues: loadedOptions.experience_values || prev.experienceValues,
                }));
            } catch (error) {
                console.error('Failed to load filter options:', error);
            } finally {
                setIsLoading(false);
            }
        };
        loadOptions();
    }, [filters?.category, filters?.experience_min, JSON.stringify(filters?.skills || [])]);

    useEffect(() => {
        if (!options.categories.length) return;
        const currentCategory = filters?.category;
        if (!currentCategory || !options.categories.includes(currentCategory)) {
            onFilterChange('category', options.categories[0]);
        }
    }, [options.categories, filters?.category, onFilterChange]);

    useEffect(() => {
        const selectedSkills = filters?.skills || [];
        if (!selectedSkills.length) return;
        const available = new Set(options.skills);
        const nextSkills = selectedSkills.filter((skill) => available.has(skill));
        if (nextSkills.length !== selectedSkills.length) {
            onFilterChange('skills', nextSkills);
        }
    }, [options.skills, filters?.skills, onFilterChange]);

    useEffect(() => {
        const minExperience = options.experienceRange?.min ?? 0;
        const maxExperience = Math.max(options.experienceRange?.max ?? minExperience, minExperience);
        const current = filters?.experience_min ?? minExperience;
        const next = Math.min(Math.max(current, minExperience), maxExperience);
        if (next !== current) {
            onFilterChange('experience_min', next);
        }
    }, [options.experienceRange, filters?.experience_min, onFilterChange]);

    const experienceMin = options.experienceRange?.min ?? 0;
    const experienceMax = Math.max(options.experienceRange?.max ?? experienceMin, experienceMin);
    const experienceMarks = useMemo(() => {
        const values = (options.experienceValues || [])
            .map((value) => Number(value))
            .filter((value) => Number.isFinite(value))
            .sort((a, b) => a - b);
        if (values.length > 0) {
            const uniqueValues = Array.from(new Set(values));
            return uniqueValues.map((value) => ({ value, label: `${value}` }));
        }
        if (experienceMax <= experienceMin) {
            return [{ value: experienceMin, label: `${experienceMin}` }];
        }
        const mid = Math.round((experienceMin + experienceMax) / 2);
        const markValues = Array.from(new Set([experienceMin, mid, experienceMax]));
        return markValues.map((value) => ({ value, label: `${value}` }));
    }, [options.experienceValues, experienceMin, experienceMax]);

    const handleSliderChange = (event, newValue) => {
        onFilterChange('experience_min', newValue);
    };

    const handleAutocompleteChange = (name, newValue) => {
        onFilterChange(name, newValue);
    };

    return (
        <Paper
            className="glass-paper"
            sx={{
                p: 3,
                mb: 4,
                width: '100%',
                position: 'relative',
                zIndex: 10
            }}
        >
            {/* Контейнер із гнучкою версткою */}
            <Box
                sx={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 3,
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%'
                }}
            >
                {/* Категорія */}
                <Box sx={{ flexBasis: { xs: '100%', md: '45%' }, flexGrow: 1 }}>
                    <Autocomplete
                        fullWidth
                        options={options.categories}
                        value={filters.category || null}
                        onChange={(e, val) => handleAutocompleteChange('category', val)}
                        loading={isLoading}
                        getOptionLabel={(option) => option || ''}
                        renderInput={(params) => (
                            <TextField {...params} label="Категорія" fullWidth />
                        )}
                    />
                </Box>

                {/* Навички */}
                <Box sx={{ flexBasis: { xs: '100%', md: '45%' }, flexGrow: 1 }}>
                    <Autocomplete
                        fullWidth
                        multiple
                        disableCloseOnSelect
                        options={options.skills}
                        value={filters.skills || []}
                        onChange={(e, val) => handleAutocompleteChange('skills', val)}
                        loading={isLoading}
                        getOptionLabel={(option) => option || ''}
                        renderOption={(props, option, { selected }) => {
                            const { key, ...optionProps } = props;
                            return (
                            <li key={key} {...optionProps}>
                                <Checkbox
                                    icon={icon}
                                    checkedIcon={checkedIcon}
                                    style={{ marginRight: 8 }}
                                    checked={selected}
                                />
                                {option}
                            </li>
                        )}}
                        renderInput={(params) => (
                            <TextField {...params} label="Навички" fullWidth />
                        )}
                    />
                </Box>

                {/* Досвід */}
                <Box
                    sx={{
                        flexBasis: { xs: '100%', md: '100%' }, // тепер займає повну ширину ряду
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        mt: 1
                    }}
                >
                    <Typography gutterBottom align="center" sx={{ mb: 1 }}>
                        Досвід (років)
                    </Typography>
                    <Slider
                        value={filters.experience_min ?? experienceMin}
                        onChange={handleSliderChange}
                        step={1}
                        marks={experienceMarks}
                        min={experienceMin}
                        max={experienceMax}
                        valueLabelDisplay="auto"
                        sx={{
                            width: '80%', // ← збільшує ширину слайдера
                            maxWidth: 600, // гарна пропорція для естетики
                        }}
                    />
                </Box>
            </Box>
        </Paper>
    );
};

export default Filters;
