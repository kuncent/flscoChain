// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title GreenEnergy 绿色能量代币（ERC20）
 * @dev 低碳出行场景下的同质化代币，单位为"点"，保留整数。
 *
 *      发行权模型（与后端 app/learning/alliance_roles.py 的四维度职能口径一致）：
 *        - owner（创世部署方 = 联盟秘书处 / 能量国库 0xadmin）：唯一能维护发行白名单、
 *          能执行 burn（销毁属治理动作，不是普通转账）；
 *        - issuers（发行白名单 = 地铁 / 公交 / 单车 / 外卖 / 回收等业务节点组织钱包）：
 *          只能按已核算的低碳行为 mint 能量，不能 burn、不能授权他人；
 *        - 其他地址（居民）：只能 transfer / approve，**不能自铸**。
 *      应用层（/api/eco/energy/issue）与合约层双重拦，避免只靠后端校验被绕过。
 */
contract GreenEnergy {
    string public name = "GreenEnergy";
    string public symbol = "GE";
    uint8  public decimals = 0;          // 整数，无小数
    uint256 public totalSupply;

    address public owner;                        // 联盟创世账户 / 能量国库
    mapping(address => bool) public issuers;     // 发行权白名单

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event EnergyMinted(address indexed to, uint256 value, string reason);
    event EnergyBurned(address indexed from, uint256 value);
    event IssuerUpdated(address indexed issuer, bool allowed);
    event OwnerHandover(address indexed oldOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "GE: not owner");
        _;
    }

    modifier onlyIssuer() {
        require(msg.sender == owner || issuers[msg.sender], "GE: not issuer");
        _;
    }

    // _initialSupply = 创世预发行量：真实商业里应传 0（能量只能由业务行为逐步发行），
    // 传正数则全部记到国库（msg.sender）名下，作为待投放储备。
    constructor(uint256 _initialSupply) public {
        owner = msg.sender;
        issuers[msg.sender] = true;
        totalSupply = _initialSupply;
        balanceOf[msg.sender] = _initialSupply;
    }

    // ---------- 发行权治理（仅 owner） ----------
    function addIssuer(address _issuer) public onlyOwner {
        require(_issuer != address(0), "GE: issuer is zero");
        issuers[_issuer] = true;
        emit IssuerUpdated(_issuer, true);
    }

    function removeIssuer(address _issuer) public onlyOwner {
        require(_issuer != address(0), "GE: issuer is zero");
        require(_issuer != owner, "GE: cannot remove owner");
        issuers[_issuer] = false;
        emit IssuerUpdated(_issuer, false);
    }

    function handoverOwner(address _newOwner) public onlyOwner {
        require(_newOwner != address(0), "GE: owner is zero");
        issuers[_newOwner] = true;
        emit OwnerHandover(owner, _newOwner);
        owner = _newOwner;
    }

    function mint(address _to, uint256 _value, string _reason) public onlyIssuer {
        require(_to != address(0), "GE: mint to zero");
        require(_value > 0, "GE: mint zero");
        totalSupply += _value;
        balanceOf[_to] += _value;
        emit EnergyMinted(_to, _value, _reason);
        emit Transfer(address(0), _to, _value);
    }

    function transfer(address _to, uint256 _value) public returns (bool) {
        require(_to != address(0), "GE: transfer to zero");
        require(balanceOf[msg.sender] >= _value, "GE: insufficient balance");
        balanceOf[msg.sender] -= _value;
        balanceOf[_to] += _value;
        emit Transfer(msg.sender, _to, _value);
        return true;
    }

    function approve(address _spender, uint256 _value) public returns (bool) {
        allowance[msg.sender][_spender] = _value;
        emit Approval(msg.sender, _spender, _value);
        return true;
    }

    function transferFrom(address _from, address _to, uint256 _value) public returns (bool) {
        require(_to != address(0), "GE: transfer to zero");
        require(balanceOf[_from] >= _value, "GE: insufficient balance");
        require(allowance[_from][msg.sender] >= _value, "GE: insufficient allowance");
        balanceOf[_from] -= _value;
        balanceOf[_to] += _value;
        allowance[_from][msg.sender] -= _value;
        emit Transfer(_from, _to, _value);
        return true;
    }

    // 销毁：退出流通、总供应量下降，属联盟治理动作（仅国库 / 创世账户可执行）
    function burn(uint256 _value) public onlyOwner {
        require(_value > 0, "GE: burn zero");
        require(balanceOf[msg.sender] >= _value, "GE: insufficient balance");
        balanceOf[msg.sender] -= _value;
        totalSupply -= _value;
        emit EnergyBurned(msg.sender, _value);
        emit Transfer(msg.sender, address(0), _value);
    }
}
