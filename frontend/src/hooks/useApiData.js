import { useState, useCallback } from 'react';

export const useApiData = (apiFunction) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async (filters) => {
        setLoading(true);
        setError(null);
        try {
            const result = await apiFunction(filters);
            setData(result);
        } catch (err) {
            setError(err);
        } finally {
            setLoading(false);
        }
    }, [apiFunction]);

    return { data, loading, error, fetchData };
};