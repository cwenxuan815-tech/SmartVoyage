-- ============================================================
-- SmartVoyage 统一建表脚本
-- 数据库: travel_rag / 字符集: utf8mb4
-- 说明: 每张表前带 DROP TABLE IF EXISTS，可重复执行；业务数据用模拟数据填充
-- ============================================================
CREATE DATABASE IF NOT EXISTS travel_rag CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE travel_rag;

DROP TABLE IF EXISTS train_tickets;
CREATE TABLE train_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    departure_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '出发城市',
    arrival_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '到达城市',
    departure_time DATETIME NOT NULL COMMENT '出发时间',
    arrival_time DATETIME NOT NULL COMMENT '到达时间',
    train_number VARCHAR(20) NOT NULL COMMENT '车次',
    seat_type VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '座位类型',
    total_seats INT NOT NULL COMMENT '总座位数',
    remaining_seats INT NOT NULL COMMENT '剩余座位数',
    price DECIMAL(10, 2) NOT NULL COMMENT '票价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY unique_train (departure_time, train_number, seat_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='火车票信息表';

DROP TABLE IF EXISTS flight_tickets;
CREATE TABLE flight_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    departure_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '出发城市',
    arrival_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '到达城市',
    departure_time DATETIME NOT NULL COMMENT '出发时间',
    arrival_time DATETIME NOT NULL COMMENT '到达时间',
    flight_number VARCHAR(20) NOT NULL COMMENT '航班号',
    cabin_type VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '舱位类型',
    total_seats INT NOT NULL COMMENT '总座位数',
    remaining_seats INT NOT NULL COMMENT '剩余座位数',
    price DECIMAL(10, 2) NOT NULL COMMENT '票价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY unique_flight (departure_time, flight_number, cabin_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='航班机票信息表';

DROP TABLE IF EXISTS concert_tickets;
CREATE TABLE concert_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    artist VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '艺人名称',
    city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '举办城市',
    venue VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '场馆',
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME NOT NULL COMMENT '结束时间',
    ticket_type VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '票类型',
    total_seats INT NOT NULL COMMENT '总座位数',
    remaining_seats INT NOT NULL COMMENT '剩余座位数',
    price DECIMAL(10, 2) NOT NULL COMMENT '票价',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY unique_concert (start_time, artist, ticket_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='演唱会门票信息表';

DROP TABLE IF EXISTS weather_data;
CREATE TABLE weather_data (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    city VARCHAR(50) NOT NULL COMMENT '城市名称',
    fx_date DATE NOT NULL COMMENT '预报日期',
    sunrise TIME COMMENT '日出时间',
    sunset TIME COMMENT '日落时间',
    moonrise TIME COMMENT '月升时间',
    moonset TIME COMMENT '月落时间',
    moon_phase VARCHAR(20) COMMENT '月相名称',
    moon_phase_icon VARCHAR(10) COMMENT '月相图标代码',
    temp_max INT COMMENT '最高温度',
    temp_min INT COMMENT '最低温度',
    icon_day VARCHAR(10) COMMENT '白天天气图标代码',
    text_day VARCHAR(20) COMMENT '白天天气描述',
    icon_night VARCHAR(10) COMMENT '夜间天气图标代码',
    text_night VARCHAR(20) COMMENT '夜间天气描述',
    wind360_day INT COMMENT '白天风向360角度',
    wind_dir_day VARCHAR(20) COMMENT '白天风向',
    wind_scale_day VARCHAR(10) COMMENT '白天风力等级',
    wind_speed_day INT COMMENT '白天风速',
    wind360_night INT COMMENT '夜间风向360角度',
    wind_dir_night VARCHAR(20) COMMENT '夜间风向',
    wind_scale_night VARCHAR(10) COMMENT '夜间风力等级',
    wind_speed_night INT COMMENT '夜间风速',
    precip DECIMAL(5,1) COMMENT '降水量',
    uv_index INT COMMENT '紫外线指数',
    humidity INT COMMENT '相对湿度',
    pressure INT COMMENT '大气压强',
    vis INT COMMENT '能见度',
    cloud INT COMMENT '云量',
    update_time DATETIME COMMENT '数据更新时间',
    UNIQUE KEY unique_city_date (city, fx_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='天气数据表';

DROP TABLE IF EXISTS car_rentals;
CREATE TABLE car_rentals (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    company VARCHAR(50) NOT NULL COMMENT '租车公司',
    pickup_city VARCHAR(50) NOT NULL COMMENT '取车城市',
    return_city VARCHAR(50) NOT NULL COMMENT '还车城市',
    pickup_date DATE NOT NULL COMMENT '取车日期',
    car_type VARCHAR(20) NOT NULL COMMENT '车型分类',
    car_model VARCHAR(50) NOT NULL COMMENT '具体车型',
    price_per_day DECIMAL(8,2) NOT NULL COMMENT '日租金',
    total_available INT NOT NULL DEFAULT 0 COMMENT '可租车辆数',
    transmission VARCHAR(20) NOT NULL COMMENT '变速箱',
    seats INT NOT NULL COMMENT '座位数',
    deposit DECIMAL(8,2) NOT NULL DEFAULT 0 COMMENT '押金',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY unique_car (company, car_model, pickup_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租车信息表';

DROP TABLE IF EXISTS insurances;
CREATE TABLE insurances (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    insurance_type VARCHAR(20) NOT NULL COMMENT '保险类型',
    name VARCHAR(100) NOT NULL COMMENT '产品名称',
    company VARCHAR(50) NOT NULL COMMENT '保险公司',
    coverage TEXT NOT NULL COMMENT '保障范围',
    price DECIMAL(8,2) NOT NULL COMMENT '价格',
    duration_days INT NOT NULL COMMENT '保障天数',
    max_coverage DECIMAL(10,2) NOT NULL COMMENT '最高赔付',
    medical_coverage DECIMAL(10,2) DEFAULT 0 COMMENT '医疗保障额度',
    baggage_coverage DECIMAL(10,2) DEFAULT 0 COMMENT '行李保障额度',
    flight_delay BOOLEAN DEFAULT FALSE COMMENT '是否含航班延误',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY unique_insurance (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='旅行保险信息表';

DROP TABLE IF EXISTS tour_groups;
CREATE TABLE tour_groups (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    tour_id VARCHAR(30) NOT NULL COMMENT '旅游团编号',
    tour_name VARCHAR(100) NOT NULL COMMENT '团名',
    city VARCHAR(50) NOT NULL COMMENT '出发城市',
    days INT NOT NULL COMMENT '行程天数',
    price DECIMAL(10,2) NOT NULL COMMENT '价格',
    total_seats INT NOT NULL COMMENT '总名额',
    remaining_seats INT NOT NULL COMMENT '剩余名额',
    agency VARCHAR(50) NOT NULL COMMENT '旅行社',
    rating DECIMAL(3,1) NOT NULL COMMENT '评分',
    departure_dates VARCHAR(200) NOT NULL COMMENT '发团日期',
    highlights VARCHAR(300) NOT NULL COMMENT '亮点标签',
    description TEXT NOT NULL COMMENT '语义检索文本',
    embedding TEXT COMMENT '向量（JSON）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY unique_tour (tour_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='旅游团信息表';

DROP TABLE IF EXISTS user_profiles;
CREATE TABLE user_profiles (
    profile_key VARCHAR(50) NOT NULL COMMENT '偏好键名',
    profile_value VARCHAR(200) NOT NULL COMMENT '偏好值',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (profile_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户偏好';

DROP TABLE IF EXISTS query_history;
CREATE TABLE query_history (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    intent_type VARCHAR(30) NOT NULL COMMENT '意图类型',
    query_content TEXT NOT NULL COMMENT '查询内容JSON',
    query_time DATETIME NOT NULL COMMENT '查询时间',
    INDEX idx_time (query_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='查询历史';

DROP TABLE IF EXISTS short_term_messages;
CREATE TABLE short_term_messages (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    role VARCHAR(10) NOT NULL COMMENT '消息角色',
    content TEXT NOT NULL COMMENT '消息内容',
    message_time VARCHAR(10) NOT NULL COMMENT '时间戳',
    message_order INT NOT NULL COMMENT '消息顺序号',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短期对话';
