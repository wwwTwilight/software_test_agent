#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
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

struct CheckoutResult {
    std::string status;
    double final_payable = 0.0;
};

// 地区判断：是否为偏远地区（新疆、西藏等）
static bool is_remote_region(const std::string& region) {
    return region == "Xinjiang" || region == "Tibet" || region == "新疆" || region == "西藏";
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

// 结算主流程：汇总金额、应用优惠券、合并运费、组装响应
static CheckoutResult checkout_buggy(const CheckoutData& req) {

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

    return {"SUCCESS", final_payable};
}

// 命令行入口：直接从标准输入读取字段
int main() {
    // 输入格式：
    // region
    // item_count
    // sku_id name price quantity weight is_special stock  (重复 item_count 行)
    // coupon_count
    // id type value min_purchase applicable_to_special expired (重复 coupon_count 行)
    CheckoutData req;
    int item_count = 0;
    int coupon_count = 0;

    if (!(std::cin >> req.region >> item_count)) {
        return 0;
    }

    req.items.reserve(std::max(0, item_count));
    for (int i = 0; i < item_count; ++i) {
        CartItem item;
        std::cin >> item.sku_id >> item.name >> item.price >> item.quantity >> item.weight >> item.is_special >> item.stock;
        req.items.push_back(item);
    }

    if (!(std::cin >> coupon_count)) {
        coupon_count = 0;
    }

    req.coupons.reserve(std::max(0, coupon_count));
    for (int i = 0; i < coupon_count; ++i) {
        Coupon coupon;
        std::cin >> coupon.id >> coupon.type >> coupon.value >> coupon.min_purchase >> coupon.applicable_to_special >> coupon.expired;
        req.coupons.push_back(coupon);
    }

    const CheckoutResult result = checkout_buggy(req);
    std::cout << "status=" << result.status << " final_payable=" << result.final_payable << std::endl;
    return 0;
}
