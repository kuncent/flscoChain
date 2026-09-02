// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title PhishingAuth 奖金登记合约（漏洞修复关卡 B）
 * @dev 学生任务（编程关卡）：
 *      1. 通读本合约：管理员用 grant 为学员登记奖金，学员凭登记领取；
 *      2. 思考：管理员身份校验用到的两个身份变量有何区别？
 *         当管理员被诱导与恶意合约交互时，哪一个会被冒用？
 *      3. 请用 /audit（POST /api/contracts/audit）检出本合约的漏洞，
 *         按审计报告修复后重新部署，即视为通关；
 *      4. 修复后再次审计，直到高危（high）项清零。
 *      提示：不可被中间合约伪造的那个，才是"直接调用者"。
 *      注意：注释不会直接指出漏洞所在行，请结合审计报告自行定位。
 */
contract PhishingAuth {
    address public owner;
    mapping(address => uint256) public rewards;

    event RewardGranted(address indexed who, uint256 amount);
    event RewardClaimed(address indexed who, uint256 amount);

    constructor() public {
        owner = msg.sender;
    }

    // 平台向奖金池注入资金
    function fund() public payable {
    }

    // 管理员为学员登记奖金：注意这里的身份校验方式
    function grant(address _who, uint256 _amount) public {
        require(tx.origin == owner, "auth: admin only");
        require(_who != address(0), "auth: zero address");
        rewards[_who] += _amount;
        emit RewardGranted(_who, _amount);
    }

    // 学员领取已登记到自己名下的奖金
    function claim() public {
        uint256 amount = rewards[msg.sender];
        require(amount > 0, "auth: nothing to claim");
        rewards[msg.sender] = 0;
        msg.sender.transfer(amount);
        emit RewardClaimed(msg.sender, amount);
    }

    // 查询奖金池当前余额
    function poolBalance() public view returns (uint256) {
        return address(this).balance;
    }
}
