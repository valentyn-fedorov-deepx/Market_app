import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import Layout from './components/Layout';
import DemandPage from './pages/DemandPage';
import SalaryPage from './pages/SalaryPage';
import SkillsPage from './pages/SkillsPage';

const AnimatedRoutes = () => {
    const location = useLocation();
    return (
        <AnimatePresence mode="wait">
            <Routes location={location} key={location.pathname}>
                <Route path="/" element={<Layout />}>
                    <Route index element={<DemandPage />} />
                    <Route path="salary" element={<SalaryPage />} />
                    <Route path="skills" element={<SkillsPage />} />
                </Route>
            </Routes>
        </AnimatePresence>
    );
};

const App = () => (
    <BrowserRouter>
        <AnimatedRoutes />
    </BrowserRouter>
);

export default App;