import { motion } from 'framer-motion';

const pageVariants = {
    initial: { opacity: 0, y: 20 },
    in: { opacity: 1, y: 0 },
    out: { opacity: 0, y: -20 },
};

const pageTransition = {
    type: 'tween',
    ease: 'anticipate',
    duration: 0.5,
};

const MotionDiv = motion.div;

const PageContainer = ({ children }) => (
    <MotionDiv
        initial="initial"
        animate="in"
        exit="out"
        variants={pageVariants}
        transition={pageTransition}
        style={{ width: '100%', maxWidth: '1400px', margin: '0 auto', padding: '0 16px' }}
    >
        {children}
    </MotionDiv>
);

export default PageContainer;
