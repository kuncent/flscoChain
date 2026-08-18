// SPDX-License-Identifier: MIT
pragma solidity ^0.4.25;

/**
 * @title PlantCertificate 植树证书（ERC721）
 * @dev 不同树种对应不同 Token ID，每个证书唯一。
 *      用户花费绿色能量兑换植树证书，管理员新增树种。
 */
contract PlantCertificate {
    string public name = "PlantCertificate";
    string public symbol = "PC";

    mapping(uint256 => address) public ownerOf;
    mapping(address => uint256) public balanceOf;
    mapping(uint256 => address) public approved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;
    mapping(uint256 => string) public tokenURI;
    mapping(uint256 => uint256) public speciesIdOf;   // tokenId => 树种ID

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event CertificateIssued(uint256 indexed tokenId, uint256 indexed speciesId, address indexed owner);

    constructor(string _name, string _symbol) public {
        name = _name;
        symbol = _symbol;
    }

    function mint(address _to, uint256 _tokenId, uint256 _speciesId, string _tokenURI) public {
        require(_to != address(0), "PC: mint to zero");
        require(ownerOf[_tokenId] == address(0), "PC: token already exists");
        ownerOf[_tokenId] = _to;
        balanceOf[_to]++;
        speciesIdOf[_tokenId] = _speciesId;
        tokenURI[_tokenId] = _tokenURI;
        emit Transfer(address(0), _to, _tokenId);
        emit CertificateIssued(_tokenId, _speciesId, _to);
    }

    function transferFrom(address _from, address _to, uint256 _tokenId) public {
        require(ownerOf[_tokenId] == _from, "PC: not owner");
        require(_to != address(0), "PC: transfer to zero");
        require(
            msg.sender == _from || approved[_tokenId] == msg.sender || isApprovedForAll[_from][msg.sender],
            "PC: not approved"
        );
        balanceOf[_from]--;
        balanceOf[_to]++;
        ownerOf[_tokenId] = _to;
        approved[_tokenId] = address(0);
        emit Transfer(_from, _to, _tokenId);
    }

    function approve(address _approved, uint256 _tokenId) public {
        require(ownerOf[_tokenId] == msg.sender, "PC: not owner");
        approved[_tokenId] = _approved;
        emit Approval(msg.sender, _approved, _tokenId);
    }

    function setApprovalForAll(address _operator, bool _approved) public {
        isApprovedForAll[msg.sender][_operator] = _approved;
        emit ApprovalForAll(msg.sender, _operator, _approved);
    }
}
