// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title GreenEnergy 绿色能量代币（ERC20）
 * @dev 低碳出行场景下的同质化代币，单位为"点"，保留整数。
 *      各联盟节点通过 mint() 向用户发放绿色能量。
 */
contract GreenEnergy {
    string public name = "GreenEnergy";
    string public symbol = "GE";
    uint8  public decimals = 0;          // 整数，无小数
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event EnergyMinted(address indexed to, uint256 value, string reason);

    constructor(uint256 _initialSupply) public {
        totalSupply = _initialSupply;
        balanceOf[msg.sender] = _initialSupply;
    }

    function mint(address _to, uint256 _value, string _reason) public {
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

    function burn(uint256 _value) public {
        require(balanceOf[msg.sender] >= _value, "GE: insufficient balance");
        balanceOf[msg.sender] -= _value;
        totalSupply -= _value;
        emit Transfer(msg.sender, address(0), _value);
    }
}
