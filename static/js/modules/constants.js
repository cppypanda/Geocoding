// Centralized constants for endpoints and common selectors

export const ENDPOINTS = {
    logout: '/logout',
    checkLogin: '/check_login_status',
    loginAccount: '/login_account',
    loginRegisterEmail: '/login_register_email',
    sendVerificationCode: '/send_verification_code',
    registerSetPassword: '/register_set_password',
    resetPassword: '/reset_password',
    changePassword: '/change_password',

    geocodeProcess: '/geocode/process',
    geocodePoiSearch: '/geocode/poi_search',
    geocodeReverse: '/geocode/reverse_geocode',
    geocodeAutoSelect: '/geocode/auto_select_point',
    geocodeConfidenceSelect: '/geocode/confidence_select_point',
    geocodeHybridSelect: '/geocode/hybrid_select_point',

    recordUsedSuffixes: '/record_used_suffixes',
    export: '/export',

    tasksBase: '/tasks/',

    // Notifications
    notificationsGet: '/user/get_notifications',
    notificationsUnreadCount: '/user/notifications/unread_count',
    notificationsMarkRead: '/user/mark_notifications_as_read',

    // User API Keys
    userKeys: '/user/keys',

    // Feedback
    submitFeedback: '/user/feedback',
    uploadFeedbackImage: '/user/upload_feedback_image',

    // Referral
    referralInfo: '/user/referral/info',
    referralBind: '/user/referral/bind',
    referralStats: '/user/referral/stats'
    ,
    // Social share
    socialShareCopy: '/user/social_share_copy'
};

export const SELECTORS = {
    resultsContainer: '#cascadeResultsContainer',
    resultsTbody: '#cascadeResultsBody',
    overviewMap: '#map',
    detailedSection: '#detailedReviewSection',
    itemCalibrationMap: '#itemCalibrationMap',
    addressSearchTools: '#addressSearchToolsContainer'
};


