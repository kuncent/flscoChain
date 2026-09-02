// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title ReentrantVault 简易存取金库（漏洞修复关卡 A）
 * @dev 学生任务（编程关卡）：
 *      1. 通读本合约，理解 deposit 与 withdraw 的完整流程；
 *      2. 思考：如果调用 withdraw 的是一个恶意合约，执行顺序里藏着什么风险？
 *      3. 请用 /audit（POST /api/contracts/audit）检出本合约的漏洞，
 *         按审计报告修复后重新部署，即视为通关；
 *      4. 修复后再次审计，直到高危（high）项清零。
 *      提示：想一想"先给钱"还是"先记账"，外部调用与状态更新谁先谁后更安全。
 *      注意：注释不会直接指出漏洞所在行，请结合审计报告自行定位。
 */
contract ReentrantVault {
    address public owner;
    mapping(address => uint256) public balances;

    event Deposited(address indexed who, uint256 amount);
    event Withdrawn(address indexed who, uint256 amount);

    constructor() public {
        owner = msg.sender;
    }

    // 存入测试币，按调用者地址记账
    function deposit() public payable {
        require(msg.value > 0, "vault: deposit zero");
        balances[msg.sender] += msg.value;
        emit Deposited(msg.sender, msg.value);
    }

    // 提现：注意本函数中"对外转账"与"更新账本"的先后顺序
    function withdraw(uint256 _amount) public {
        require(balances[msg.sender] >= _amount, "vault: insufficient balance");
        if (!msg.sender.call.value(_amount)()) revert();
        balances[msg.sender] -= _amount;
        emit Withdrawn(msg.sender, _amount);
    }

    // 查询金库当前持有的总余额
    function vaultBalance() public view returns (uint256) {
        return address(this).balance;
    }
}
