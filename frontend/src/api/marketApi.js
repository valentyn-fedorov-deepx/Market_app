import axios from 'axios';
import { stringify } from 'qs';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    paramsSerializer: (params) => stringify(params, { arrayFormat: 'repeat' }),
});

const fetchData = async (endpoint, params) => {
    try {
        const response = await apiClient.get(endpoint, { params });
        return response.data;
    } catch (error) {
        console.error(`Error fetching from ${endpoint}:`, error);
        throw error;
    }
};

const postData = async (endpoint, payload = {}) => {
    try {
        const response = await apiClient.post(endpoint, payload);
        return response.data;
    } catch (error) {
        console.error(`Error posting to ${endpoint}:`, error);
        throw error;
    }
};

export const getFilterOptions = (filters) => fetchData('/filters/options', filters);
export const getDemandData = (filters) => fetchData('/demand/', filters);
export const getSalaryData = (filters) => fetchData('/salary/', filters);
export const getSkillsData = (filters) => fetchData('/skills/', filters);

export const getSystemStatus = () => fetchData('/system/data-status');
export const refreshSystemData = (payload) => postData('/system/refresh', payload);

export const getAssistantInsights = (category) =>
    fetchData('/assistant/insights', category ? { category } : undefined);
export const createAssistantReport = (payload) => postData('/assistant/report', payload);
export const chatWithAssistant = (payload) => postData('/assistant/chat', payload);
