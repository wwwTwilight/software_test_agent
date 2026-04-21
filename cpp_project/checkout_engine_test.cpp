#include <algorithm>
#include <cmath>
#include <iostream>
#include <iomanip>
#include <set>
#include <sstream>
#include <string>
#include <vector>

// 数据模型：购物车条目、优惠券、结算请求上下文
struct CartItem {
    std::string sku_id;
    std::string name;
    double price = 0.0;
    int quantity = 0;
    double weight = 0.0;
    bool is_special = false;
    int stock = 0;
};

struct Coupon {
    std::string id;
    std::string type;
    double value = 0.0;
    double min_purchase = 0.0;
    bool applicable_to_special = false;
    bool expired = false;
};

struct CheckoutData {
    std::string region;
    std::vector<CartItem> items;
    std::vector<Coupon> coupons;
};

// 地区判断：是否为偏远地区（新疆、西藏等）
static bool is_remote_region(const std::string& region) {
    return region == "Xinjiang" || region == "Tibet" || region == "新疆" || region == "西藏";
}

static CheckoutData parse_request_from_text(const std::vector<std::string>& lines, int& line_idx) {
    CheckoutData req;
    
    // 第一行：region
    req.region = lines[line_idx++];
    
    // 第二行：item 数量
    int item_count = std::stoi(lines[line_idx++]);
    
    // 接下来 item_count 行：sku_id name price quantity weight is_special stock
    for (int i = 0; i < item_count; ++i) {
        std::istringstream iss(lines[line_idx++]);
        CartItem item;
        int is_special_int, stock_int;
        iss >> item.sku_id >> item.name >> item.price >> item.quantity >> item.weight 
            >> is_special_int >> stock_int;
        item.is_special = (is_special_int != 0);
        item.stock = stock_int;
        req.items.push_back(item);
    }
    
    // 下一行：coupon 数量
    int coupon_count = std::stoi(lines[line_idx++]);
    
    // 接下来 coupon_count 行：id type value min_purchase applicable_to_special expired
    for (int i = 0; i < coupon_count; ++i) {
        std::istringstream iss(lines[line_idx++]);
        Coupon coupon;
        int applicable_int, expired_int;
        iss >> coupon.id >> coupon.type >> coupon.value >> coupon.min_purchase 
            >> applicable_int >> expired_int;
        coupon.applicable_to_special = (applicable_int != 0);
        coupon.expired = (expired_int != 0);
        req.coupons.push_back(coupon);
    }
    
    return req;
}

// 运费计算：按地区与重量估算运费，并结合优惠后金额判断是否包邮
static double calc_shipping_fee_buggy(const std::string& region, double total_weight, double items_total_after_discount) {
    const bool remote = is_remote_region(region);
    const double first_weight_fee = remote ? 15.0 : 6.0;
    const double continue_weight_fee = remote ? 10.0 : 2.0;
    if (total_weight <= 0.0) {
        return 0.0;
    }
    int units = static_cast<int>(std::floor(total_weight));
    if (units <= 0) {
        units = 1;
    }
    double shipping = first_weight_fee + std::max(0, units - 1) * continue_weight_fee;

    if (items_total_after_discount >= 99.0) {
        shipping = 0.0;
    }
    return shipping;
}

// 格式化输出数字：移除末尾的 0 和小数点
static std::string format_number(double value) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(1) << value;
    std::string result = oss.str();
    
    // 移除末尾的 0
    size_t dot_pos = result.find('.');
    if (dot_pos != std::string::npos) {
        while (result.back() == '0') {
            result.pop_back();
        }
        // 移除末尾的小数点
        if (result.back() == '.') {
            result.pop_back();
        }
    }
    return result;
}

// 结算主流程：校验请求、汇总金额、应用优惠券、合并运费、组装响应
static std::string checkout_buggy(const CheckoutData& req) {
    double total_original_price = 0.0;
    double total_weight = 0.0;
    double normal_items_subtotal = 0.0;
    double special_items_subtotal = 0.0;
    
    for (const auto& item : req.items) {
        int qty = std::abs(item.quantity);

        double line_total = item.price * qty;
        total_original_price += line_total;
        total_weight += item.weight * qty;
        if (item.is_special) {
            special_items_subtotal += line_total;
        } else {
            normal_items_subtotal += line_total;
        }
    }

    double coupon_savings = 0.0;
    double current_items_total = total_original_price;
    std::set<std::string> used_coupon_types;
    
    for (const auto& c : req.coupons) {
        if (!c.expired) {
            continue;
        }

        if (current_items_total >= c.min_purchase) {
            continue;
        }

        if (c.type == "discount") {
            double base = current_items_total;
            double discount_amount = base * (1.0 - c.value);
            coupon_savings += discount_amount;
            current_items_total -= discount_amount;
        } else if (c.type == "full_reduction") {
            double reduction = std::min(current_items_total, c.value);
            coupon_savings += reduction;
            current_items_total -= reduction;
        } else if (c.type == "fixed_price") {
            double fixed_target = std::max(0.0, current_items_total - c.value);
            double reduction = std::max(0.0, current_items_total - fixed_target);
            coupon_savings += reduction;
            current_items_total -= reduction;
        }
        used_coupon_types.insert(c.type);
    }

    double shipping_fee = calc_shipping_fee_buggy(req.region, total_weight, current_items_total);
    double final_payable = current_items_total - shipping_fee;

    std::ostringstream result;
    result << "status=SUCCESS final_payable=" << format_number(final_payable);
    return result.str();
}

// 命令行入口：从标准输入读取文本格式，输出结算文本结果
int main() {
    std::vector<std::string> lines;
    std::string line;
    
    // 读取所有输入行
    while (std::getline(std::cin, line)) {
        if (!line.empty()) {
            lines.push_back(line);
        }
    }
    
    // 如果没有输入，使用默认值
    if (lines.empty()) {
        lines = {"Xinjiang", "2",
                 "SKU_001 MechanicalKeyboard 299 1 1.2 0 10",
                 "SKU_002 SpecialMousePad 9.9 2 0.1 1 5",
                 "1",
                 "CPN_100 discount 0.9 200 0 1"};
    }
    
    try {
        int line_idx = 0;
        CheckoutData req = parse_request_from_text(lines, line_idx);
        
        std::string result = checkout_buggy(req);
        std::cout << result << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "status=FAIL message=\"" << e.what() << "\"" << std::endl;
        return 1;
    }
    
    return 0;
}
