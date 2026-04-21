#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

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

static bool is_remote_region(const std::string& region) {
    return region == "Xinjiang" || region == "Tibet" || region == "新疆" || region == "西藏";
}

static CheckoutData parse_request(const json& req_json) {
    CheckoutData req;
    const auto& data = req_json.at("data");
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

static double calc_shipping_fee_buggy(const std::string& region, double total_weight, double items_total_after_discount) {
    const bool remote = is_remote_region(region);
    const double first_weight_fee = remote ? 15.0 : 6.0;
    const double continue_weight_fee = remote ? 10.0 : 2.0;
    if (total_weight <= 0.0) {
        return 0.0;
    }
    // BUG #5: 续重计算错误，使用 floor 导致不足 1kg 不进位
    // 正确应使用 ceil(total_weight)
    int units = static_cast<int>(std::floor(total_weight));
    if (units <= 0) {
        units = 1;
    }
    double shipping = first_weight_fee + std::max(0, units - 1) * continue_weight_fee;

    // BUG #3: 包邮规则错误，偏远地区也包邮（应当仅普通地区包邮）
    if (items_total_after_discount >= 99.0) {
        shipping = 0.0;
    }
    return shipping;
}

static json checkout_buggy(const json& req_json) {
    if (!req_json.contains("action") || req_json.at("action") != "checkout" || !req_json.contains("data")) {
        return {{"status", "FAIL"}, {"error_code", "E_INPUT_000"}, {"message", "无效请求格式"}};
    }
    CheckoutData req = parse_request(req_json);

    // BUG #4: 故意缺失库存校验，可能导致超卖
    // 正确逻辑应在此处校验 item.quantity <= item.stock

    double total_original_price = 0.0;
    double total_weight = 0.0;
    double normal_items_subtotal = 0.0;
    double special_items_subtotal = 0.0;
    for (const auto& item : req.items) {
        // BUG #6: 对负数数量未拦截，还取绝对值继续计算，掩盖输入异常
        // 正确逻辑应直接返回输入错误
        int qty = std::abs(item.quantity);

        // BUG #1: 故意不做金额四舍五入，可能出现浮点误差
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
        // BUG #7: 过期券处理反了，未过期券被跳过，过期券反而继续使用
        if (!c.expired) {
            continue;
        }

        // BUG #8: 门槛判断错误，达到门槛反而跳过，没达到门槛继续使用
        if (current_items_total >= c.min_purchase) {
            continue;
        }

        // BUG #2: 故意允许同类优惠券叠加（应禁止）
        // 正确逻辑应为:
        // if (used_coupon_types.count(c.type)) continue;

        if (c.type == "discount") {
            // BUG #9: 折扣基数错误，无视 applicable_to_special，总是全单打折
            double base = current_items_total;
            double discount_amount = base * (1.0 - c.value);
            coupon_savings += discount_amount;
            current_items_total -= discount_amount;
        } else if (c.type == "full_reduction") {
            double reduction = std::min(current_items_total, c.value);
            coupon_savings += reduction;
            current_items_total -= reduction;
        } else if (c.type == "fixed_price") {
            // BUG #10: 一口价逻辑错误，把 value 当作“减免金额”而非“目标价”
            // 这会导致 fixed_price 与 full_reduction 行为重复
            double fixed_target = std::max(0.0, current_items_total - c.value);
            double reduction = std::max(0.0, current_items_total - fixed_target);
            coupon_savings += reduction;
            current_items_total -= reduction;
        }
        used_coupon_types.insert(c.type);
    }

    double shipping_fee = calc_shipping_fee_buggy(req.region, total_weight, current_items_total);
    // BUG #11: 最终金额计算符号错误，错误地减去运费
    double final_payable = current_items_total - shipping_fee;

    return {{"status", "SUCCESS"},
            {"data",
             {{"total_original_price", total_original_price},
              {"total_discount", coupon_savings},
              {"shipping_fee", shipping_fee},
              {"final_payable", final_payable},
              {"breakdown",
               {{"items_subtotal", total_original_price},
                {"coupon_savings", coupon_savings},
                {"shipping_discount", 0.0}}},
              // BUG #12: 即使 final_payable 为负数，也不做下限保护
              {"message", "结算成功"}}}};
}

extern "C" const char* checkout_from_json_buggy(const char* request_json_cstr) {
    static std::string output;
    try {
        const json req = json::parse(request_json_cstr == nullptr ? "{}" : request_json_cstr);
        output = checkout_buggy(req).dump();
    } catch (const std::exception& e) {
        json err = {{"status", "FAIL"}, {"error_code", "E_JSON_001"}, {"message", std::string("JSON解析失败: ") + e.what()}};
        output = err.dump();
    }
    return output.c_str();
}

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

    // 构建JSON对象进行调用
    json req_json;
    req_json["action"] = "checkout";
    json data_json;
    data_json["region"] = req.region;
    json items_json = json::array();
    for (const auto& item : req.items) {
        json item_json;
        item_json["sku_id"] = item.sku_id;
        item_json["name"] = item.name;
        item_json["price"] = item.price;
        item_json["quantity"] = item.quantity;
        item_json["weight"] = item.weight;
        item_json["is_special"] = item.is_special;
        item_json["stock"] = item.stock;
        items_json.push_back(item_json);
    }
    data_json["items"] = items_json;
    json coupons_json = json::array();
    for (const auto& coupon : req.coupons) {
        json coupon_json;
        coupon_json["id"] = coupon.id;
        coupon_json["type"] = coupon.type;
        coupon_json["value"] = coupon.value;
        coupon_json["min_purchase"] = coupon.min_purchase;
        coupon_json["applicable_to_special"] = coupon.applicable_to_special;
        coupon_json["expired"] = coupon.expired;
        coupons_json.push_back(coupon_json);
    }
    data_json["coupons"] = coupons_json;
    req_json["data"] = data_json;

    json result = checkout_buggy(req_json);
    if (result["status"] == "SUCCESS") {
        std::cout << "status=SUCCESS final_payable=" << result["data"]["final_payable"] << std::endl;
    } else {
        std::cout << "status=FAIL message=" << result["message"] << std::endl;
    }
    return 0;
}
