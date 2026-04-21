#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

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

// 请求解析：从 JSON 中读取 data、items、coupons
static CheckoutData parse_request(const json& req_json) {
    CheckoutData req;
    const json& data = req_json.contains("data") ? req_json.at("data") : req_json;
    req.region = data.value("region", "");

    for (const auto& x : data.at("items")) {
        CartItem i;
        i.sku_id = x.value("sku_id", "");
        i.name = x.value("name", "");
        i.price = x.value("price", 0.0);
        i.quantity = x.value("quantity", 0);
        i.weight = x.value("weight", 0.0);
        i.is_special = x.value("is_special", false);
        i.stock = x.value("stock", 0);
        req.items.push_back(i);
    }

    for (const auto& x : data.value("coupons", json::array())) {
        Coupon c;
        c.id = x.value("id", "");
        c.type = x.value("type", "");
        c.value = x.value("value", 0.0);
        c.min_purchase = x.value("min_purchase", 0.0);
        c.applicable_to_special = x.value("applicable_to_special", false);
        c.expired = x.value("expired", false);
        req.coupons.push_back(c);
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

// 结算主流程：校验请求、汇总金额、应用优惠券、合并运费、组装响应
static json checkout_buggy(const json& req_json) {
    CheckoutData req = parse_request(req_json);

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

    return {{"status", "SUCCESS"}, {"final_payable", final_payable}};
}


// C 接口：供 Python 等通过 JSON 字符串调用
extern "C" const char* checkout_from_json_test(const char* request_json_cstr) {
    static std::string output;
    try {
        const json req = json::parse(request_json_cstr == nullptr ? "{}" : request_json_cstr);
        output = checkout_buggy(req).dump();
    } catch (const std::exception& e) {
        json err = {{"status", "FAIL"}, {"message", std::string("JSON解析失败: ") + e.what()}};
        output = err.dump();
    }
    return output.c_str();
}

// 命令行入口：从标准输入读取 JSON，输出结算 JSON
int main() {
    std::ostringstream ss;
    ss << std::cin.rdbuf();
    const std::string input = ss.str().empty() ? R"({
  "region": "Xinjiang",
  "items": [
    {"sku_id":"SKU_001","name":"机械键盘","price":299.00,"quantity":1,"weight":1.2,"is_special":false,"stock":0},
    {"sku_id":"SKU_002","name":"特价鼠标垫","price":9.90,"quantity":2,"weight":0.1,"is_special":true,"stock":1}
  ],
  "coupons": [
    {"id":"CPN_A","type":"full_reduction","value":20,"min_purchase":100,"applicable_to_special":false},
    {"id":"CPN_B","type":"full_reduction","value":10,"min_purchase":100,"applicable_to_special":false}
  ]
})"
                                       : ss.str();
    std::cout << checkout_from_json_test(input.c_str()) << std::endl;
    return 0;
}
